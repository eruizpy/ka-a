# ka-a contributor instructions

- Work only in this project; VISEP CRM and other sibling repositories are separate.
- Use a task branch/worktree. Write/update a proportional spec before changing
  behavior. Record meaningful RED/GREEN evidence and run local unit/integration
  and browser checks for affected flows.
- Keep Python as the main stack and Raspberry Pi OS Lite 64-bit as the base. The
  dashboard is local, responsive, and Spanish. Source comments and docs are English.
- Simulation is the default. Never connect equipment, flash a device, provision AWS,
  change hardware opt-ins, energize motors, or publish/deploy without user scope.
- Preserve normally-off outputs, exclusive actuator ownership, conservative water
  accounting, persistent deduplication, calibration gates, and latched stops.
- Do not weaken a limit to make a test pass. An unrun Pi/GPIO/electrical/plant/AWS
  check remains unverified even if the simulated UI and API pass.
- Keep credentials, local configuration, real readings, and private certificates out
  of Git. No public Internet exposure or automatic port forwarding.
- Use `make test`, `make browser`, and `make check`; browser tests use a disposable
  simulation and must not target an operational station.
