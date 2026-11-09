"use strict";

const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let csrf = "",
  snapshot = null,
  selectedPlant = null,
  waterRequest = null,
  refreshRunning = false;
const messages = {
  disarmed: "Primero habilitá el riego.",
  emergency_stop: "Liberá la parada de emergencia antes de continuar.",
  calibration_required:
    "Confirmá la calibración de la sonda y el caudal de la bomba.",
  invalid_calibration:
    "Las lecturas seca y húmeda deben diferir al menos 50 mV.",
  invalid_thresholds:
    "El umbral de inicio debe ser menor que el corte por humedad.",
  invalid_profile: "Revisá los valores del perfil.",
  invalid_flow: "Revisá el caudal medido.",
  volume_limit: "La dosis supera el límite por evento.",
  runtime_limit: "La dosis supera el tiempo máximo de bomba.",
  daily_limit: "El volumen supera el presupuesto diario de agua.",
  minimum_interval: "Todavía no pasó el intervalo mínimo entre riegos.",
  tank_empty: "El depósito está vacío o su sensor está desconectado.",
  leak_detected: "Se detectó una fuga o el circuito de seguridad está abierto.",
  sensor_stale: "Faltan lecturas recientes. Revisá el controlador.",
  controller_offline: "El controlador no está conectado o está en otro modo.",
  soil_too_wet: "La humedad alcanzó el límite de seguridad.",
  profile_conflict: "El perfil cambió. Cerrá y volvé a abrir la configuración.",
  plant_busy: "Esperá a que termine la dosis antes de cambiar el perfil.",
  controller_busy:
    "Esperá a que el controlador confirme que la bomba está apagada.",
  invalid_credentials: "Contraseña incorrecta.",
  login_rate_limit: "Demasiados intentos. Esperá un minuto.",
  setup_required:
    "Primero ejecutá kaa setup en la estación para crear tu contraseña.",
  sensor_error:
    "Error de lectura. Revisá sensores y liberá la parada después de corregirlo.",
  hardware_error: "Falló el controlador de hardware. Revisá las conexiones.",
  interrupted_dose:
    "Un reinicio interrumpió una dosis. Revisá la planta antes de liberar la parada.",
  shutdown_unconfirmed:
    "No se pudo confirmar el apagado. Cortá la alimentación de las bombas.",
  outside_schedule: "Fuera del horario de riego automático.",
};
const stateNames = {
  queued: "En cola",
  running: "En curso",
  completed: "Finalizada",
  cancelled: "Cancelada",
  interrupted: "Interrumpida",
};
function requestUUID() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
const eventNames = {
  controller_started: "Controlador iniciado",
  profile_updated: "Perfil actualizado",
  armed: "Riego habilitado",
  disarmed: "Riego deshabilitado",
  stop: "Parada de seguridad",
  stop_reset: "Parada liberada",
  dose_queued: "Dosis solicitada",
  dose_completed: "Dosis finalizada",
  dose_interrupted: "Dosis interrumpida",
};
function notify(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function api(path, method = "GET", body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "No se pudo contactar con la estación. Los datos pueden estar desactualizados.",
    );
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login") showLogin();
    const code = result.error || result.detail;
    throw new Error(
      messages[code] ||
        (response.status === 422
          ? "Revisá los valores ingresados."
          : `La estación rechazó la operación (${response.status}).`),
    );
  }
  return result;
}
function showLogin() {
  csrf = "";
  snapshot = null;
  selectedPlant = null;
  document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  $("#application").hidden = true;
  $("#login-screen").hidden = false;
  $("#plant-cards").replaceChildren();
  $("#plant-list").replaceChildren();
  $("#commands").replaceChildren();
  $("#events").replaceChildren();
}
function showApplication() {
  $("#login-screen").hidden = true;
  $("#application").hidden = false;
}
function dateLabel(timestamp) {
  return new Intl.DateTimeFormat("es-PY", {
    timeZone: snapshot?.timezone || "America/Asuncion",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp * 1000));
}
function chart(plant) {
  if (!plant.history.length)
    return '<p class="muted">Todavía no hay historial.</p>';
  const values = plant.history.map((r) => r.raw);
  const lo = Math.min(...values) - 40,
    hi = Math.max(...values) + 40;
  const points = values
    .map(
      (value, index) =>
        `${values.length === 1 ? 0 : (index / (values.length - 1)) * 400},${34 - ((value - lo) / (hi - lo)) * 28}`,
    )
    .join(" ");
  return `<svg class="sparkline" viewBox="0 0 400 38" preserveAspectRatio="none" role="img" aria-label="Últimas lecturas reales recibidas de la sonda"><polyline points="${points}"/></svg>`;
}
function card(plant) {
  const calibrated = plant.calibration_confirmed && plant.flow_confirmed;
  const canWater =
    snapshot.armed &&
    !snapshot.estop &&
    !snapshot.fault &&
    !plant.stale &&
    calibrated &&
    snapshot.controller_online;
  const status = plant.stale
    ? "Sin lectura reciente"
    : calibrated
      ? "Calibración confirmada"
      : "Pendiente de calibrar";
  const level = plant.moisture;
  return `<article class="plant-card" data-plant="${escapeHTML(plant.id)}">
    <div class="plant-visual"><span class="pill ${calibrated ? "" : "warning"}">${escapeHTML(status)}</span><img src="/static/bonsai.svg" alt="Ilustración de junípero"></div>
    <div class="plant-content"><div class="plant-header"><div><h2>${escapeHTML(plant.name)}</h2><p>${escapeHTML(plant.location)}</p></div><button class="icon-button" data-configure="${plant.id}" aria-label="Configurar ${escapeHTML(plant.name)}">⚙</button></div>
      <div class="plant-reading"><strong>${level === null ? "—" : level + "%"}</strong><small>índice de humedad</small><span>${plant.reading ? Math.round(plant.reading.raw) + " mV" : "Sin lectura"}</span></div>
      <progress class="moisture-bar" max="100" value="${level ?? 0}" aria-label="Índice relativo de humedad"></progress>
      <div class="plant-meta"><span>Inicio: ${plant.dry_threshold}% · corte: ${plant.wet_cutoff}%</span><span>${plant.automatic ? "Automático activado" : "Automático desactivado"}</span></div>
      ${chart(plant)}<div class="plant-bottom"><small>${plant.used_today_ml} / ${plant.daily_limit_ml} ml reservados hoy</small><button class="button secondary" data-water="${plant.id}" ${canWater ? "" : "disabled"}>Solicitar riego ↗</button></div>
    </div></article>`;
}
function render() {
  const s = snapshot,
    first = s.plants[0]?.reading;
  $("#sidebar-mode").textContent =
    s.mode === "simulation"
      ? "Simulación · sin GPIO"
      : "Raspberry Pi · hardware";
  $("#mode-banner").textContent =
    s.mode === "simulation"
      ? "SIMULACIÓN · Los datos son de prueba. No se acciona hardware."
      : "HARDWARE REAL · Las órdenes pueden accionar las bombas conectadas.";
  $("#mode-banner").className =
    "notice " + (s.mode === "simulation" ? "simulation" : "danger");
  $("#connection").textContent = s.controller_online
    ? "Controlador conectado"
    : "Controlador sin conexión";
  $("#connection").className =
    "connection" + (s.controller_online ? " online" : "");
  $("#today").textContent = new Intl.DateTimeFormat("es-PY", {
    timeZone: s.timezone,
    weekday: "long",
    day: "numeric",
    month: "long",
  })
    .format(new Date(s.server_time * 1000))
    .toUpperCase();
  $("#plant-count").textContent = s.plants.length;
  $("#temperature").textContent = first
    ? first.temperature.toFixed(1) + " °C"
    : "—";
  $("#humidity").textContent = first
    ? first.humidity.toFixed(0) + "% de humedad ambiental"
    : "Sin lecturas";
  $("#water-today").textContent =
    s.plants.reduce((total, p) => total + p.used_today_ml, 0) + " ml";
  $("#tank").textContent = first
    ? first.tank_ok
      ? "Con agua"
      : "Revisar"
    : "—";
  $("#leak").textContent = first
    ? first.leak
      ? "Alerta de fuga"
      : "Sin fugas detectadas"
    : "Sin lecturas";
  $("#plant-cards").innerHTML = s.plants.map(card).join("");
  $("#plant-list").innerHTML = s.plants.map(card).join("");
  $("#armed-badge").textContent = s.estop
    ? "PARADA BLOQUEADA"
    : s.armed
      ? "HABILITADO"
      : "DESHABILITADO";
  $("#armed-badge").className =
    "pill" + (s.estop ? " stopped" : s.armed ? "" : " warning");
  $("#arm").textContent = s.armed ? "Deshabilitar riego" : "Habilitar riego";
  $("#arm").disabled = s.estop || !!s.fault || !s.controller_online;
  $("#reset").hidden = !s.estop && !s.fault;
  $("#fault-banner").hidden = !s.estop && !s.fault;
  $("#fault-banner").textContent = s.fault
    ? messages[s.fault] || s.fault
    : "Parada de emergencia activada. Revisá el sistema antes de liberarla.";
  $("#commands").innerHTML = s.commands.length
    ? s.commands
        .map(
          (c) =>
            `<tr><td>${dateLabel(c.created_at)}</td><td>${escapeHTML(s.plants.find((p) => p.id === c.plant_id)?.name || c.plant_id)}</td><td>${c.volume_ml} ml</td><td>${escapeHTML(stateNames[c.status] || c.status)}${c.reason ? " · " + escapeHTML(messages[c.reason] || c.reason) : ""}</td></tr>`,
        )
        .join("")
    : '<tr><td colspan="4">Todavía no hay dosis registradas.</td></tr>';
  $("#events").innerHTML = s.events.length
    ? s.events
        .map(
          (e) =>
            `<div class="event"><span>${escapeHTML(eventNames[e.kind] || e.kind)}</span><small>${dateLabel(e.recorded_at)}</small></div>`,
        )
        .join("")
    : '<p class="muted">Todavía no hay actividad.</p>';
  const cloudNames = {
    disabled: "Desactivada",
    connected: "Conectada",
    offline: "Sin conexión",
    connecting: "Conectando",
  };
  const details = {
    Modo: s.mode === "simulation" ? "Simulación" : "Raspberry Pi 4",
    Controlador: s.controller_online ? "Activo" : "Desconectado",
    "Zona horaria": s.timezone,
    "AWS IoT": cloudNames[s.cloud] || s.cloud,
    "Mensajes pendientes": s.outbox_pending,
    Persistencia: "SQLite local · el riego no depende de Internet",
  };
  $("#station-details").innerHTML = Object.entries(details)
    .map(
      ([key, value]) =>
        `<dt>${escapeHTML(key)}</dt><dd>${escapeHTML(value)}</dd>`,
    )
    .join("");
  $("#simulation-panel").hidden = s.mode !== "simulation";
  $("#last-update").textContent =
    "Última consulta · " + dateLabel(s.server_time);
}
async function refresh() {
  if (!csrf || refreshRunning) return;
  refreshRunning = true;
  try {
    snapshot = await api("/api/status");
    render();
  } catch (error) {
    if (csrf) {
      $("#connection").textContent = "Estación sin conexión";
      $("#connection").className = "connection";
      $("#fault-banner").hidden = false;
      $("#fault-banner").textContent = error.message;
      $("#arm").disabled = true;
      document
        .querySelectorAll("[data-water]")
        .forEach((b) => (b.disabled = true));
    }
  } finally {
    refreshRunning = false;
  }
}
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const result = await api("/api/login", "POST", {
      password: $("#password").value,
    });
    csrf = result.csrf;
    $("#password").value = "";
    $("#login-error").textContent = "";
    showApplication();
    await refresh();
  } catch (error) {
    $("#login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", "POST");
    showLogin();
  } catch (error) {
    notify(error.message);
  }
});
document.querySelectorAll("[data-view]").forEach((button) => {
  button.setAttribute("aria-label", button.textContent.trim());
  button.addEventListener("click", () => {
    document
      .querySelectorAll(".view")
      .forEach((v) => (v.hidden = v.id !== "view-" + button.dataset.view));
    document
      .querySelectorAll("[data-view]")
      .forEach((b) => b.classList.toggle("active", b === button));
    $("#breadcrumb").textContent = button.textContent.trim().toUpperCase();
  });
});
document
  .querySelectorAll("[data-close]")
  .forEach((b) =>
    b.addEventListener("click", () =>
      document.getElementById(b.dataset.close).close(),
    ),
  );
document.addEventListener("click", (event) => {
  const configure = event.target.closest("[data-configure]"),
    water = event.target.closest("[data-water]");
  if (!snapshot) return;
  if (configure) {
    selectedPlant = snapshot.plants.find(
      (p) => p.id === configure.dataset.configure,
    );
    const form = $("#profile-form");
    $("#profile-title").textContent = selectedPlant.name;
    form.elements.dose_ml.max = snapshot.safety.max_event_ml;
    form.elements.daily_limit_ml.max = snapshot.safety.max_daily_ml;
    for (const input of form.querySelectorAll("input")) {
      if (input.name === "minimum_interval_minutes")
        input.value = selectedPlant.minimum_interval_seconds / 60;
      else if (input.type === "checkbox")
        input.checked = !!selectedPlant[input.name];
      else input.value = selectedPlant[input.name] ?? "";
    }
    $("#profile-error").textContent = "";
    $("#profile-dialog").showModal();
  }
  if (water && !water.disabled) {
    selectedPlant = snapshot.plants.find((p) => p.id === water.dataset.water);
    waterRequest = requestUUID();
    $("#water-title").textContent = "Regar · " + selectedPlant.name;
    $("#volume").value = selectedPlant.dose_ml;
    $("#volume").max = selectedPlant.dose_ml;
    $("#water-error").textContent = "";
    $("#water-dialog").showModal();
  }
});
$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const body = { revision: selectedPlant.revision };
  for (const input of event.target.querySelectorAll("input")) {
    if (input.name === "name") body.name = input.value;
    else if (input.type === "checkbox") body[input.name] = input.checked;
    else if (input.name === "minimum_interval_minutes")
      body.minimum_interval_seconds = Number(input.value) * 60;
    else body[input.name] = input.value === "" ? null : Number(input.value);
  }
  try {
    await api(`/api/plants/${selectedPlant.id}`, "PATCH", body);
    $("#profile-dialog").close();
    notify("Perfil guardado");
    await refresh();
  } catch (error) {
    $("#profile-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#water-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    await api(`/api/plants/${selectedPlant.id}/water`, "POST", {
      volume_ml: Number($("#volume").value),
      request_id: waterRequest,
    });
    $("#water-dialog").close();
    notify(
      "Dosis registrada. El controlador volverá a comprobar la seguridad.",
    );
    await refresh();
  } catch (error) {
    $("#water-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
async function control(action) {
  try {
    await api("/api/control/" + action, "POST");
    await refresh();
  } catch (error) {
    notify(error.message);
  }
}
$("#arm").addEventListener("click", () =>
  control(snapshot.armed ? "disarm" : "arm"),
);
$("#emergency").addEventListener("click", () => control("stop"));
$("#reset").addEventListener("click", () => control("reset"));
$("#refresh").addEventListener("click", refresh);
$("#demo-calibrate").addEventListener("click", async () => {
  try {
    for (const p of snapshot.plants)
      await api(`/api/plants/${p.id}`, "PATCH", {
        revision: p.revision,
        dry_raw: 2500,
        wet_raw: 1000,
        calibration_confirmed: true,
        flow_ml_min: 60,
        flow_confirmed: true,
        automatic: false,
      });
    notify("Calibración de ejemplo aplicada sólo a la simulación");
    await refresh();
  } catch (error) {
    notify(error.message);
  }
});
$("#simulate-leak").addEventListener("click", async () => {
  try {
    await api("/api/simulation", "PUT", { tank_ok: true, leak: true });
    notify("Fuga simulada. El controlador detendrá el riego.");
  } catch (error) {
    notify(error.message);
  }
});
$("#restore-sensors").addEventListener("click", async () => {
  try {
    await api("/api/simulation", "PUT", {
      tank_ok: true,
      leak: false,
      raw: { "juniper-10": 2100, "juniper-7": 1900 },
    });
    notify("Sensores restaurados. Liberá la parada si corresponde.");
  } catch (error) {
    notify(error.message);
  }
});
async function boot() {
  try {
    const result = await api("/api/session");
    csrf = result.csrf;
    showApplication();
    await refresh();
  } catch {
    showLogin();
  }
}
setInterval(refresh, 2000);
boot();
