# Optional AWS IoT Core telemetry

AWS integration is disabled by default. Version 0.1 publishes telemetry only; cloud
commands, Device Shadow configuration changes, and remote pump control are not
implemented. A compromised cloud topic must not become a watering command.

## Provision separately

1. Choose your AWS account and region. Create one Thing/client identity, for example
   `ka-a-balcony`, and an active device certificate with its private key.
2. Obtain the AWS IoT ATS data endpoint and the appropriate Amazon root CA through
   the AWS console/documentation. Verify them; do not download unreviewed keys.
3. Replace `REGION` and `ACCOUNT_ID` in
   `infra/aws/iot-policy.template.json`. Keep client ID/topic aligned with the app.
   Attach this least-privilege policy to the device certificate. There is no `*`
   topic, subscribe, receive, shadow, or device-management permission.
4. Put device files outside Git, for example `/etc/kaa/certs/`. Grant the `kaa`
   service read access to its certificate/private key and keep key permissions at
   `0600`, owned by `kaa`. Never paste the private key into YAML, logs, or the UI.
5. Configure paths, not credentials, in `/etc/kaa/config.yaml`:

```yaml
mqtt_endpoint: YOUR_ENDPOINT-ats.iot.YOUR_REGION.amazonaws.com
mqtt_client_id: ka-a-balcony
mqtt_ca: /etc/kaa/certs/AmazonRootCA1.pem
mqtt_cert: /etc/kaa/certs/device.pem.crt
mqtt_key: /etc/kaa/certs/private.pem.key
telemetry_interval_seconds: 300
```

The optional `aws` extra installs Paho MQTT. The client uses mutual TLS on port 8883,
hostname/certificate verification, no retained payload, and QoS 1. The endpoint
must be an AWS IoT hostname. Client certificate and policy provisioning are never
executed by the app or by tests.

## Delivery and offline behavior

The controller collects readings locally regardless of network connectivity.
Telemetry is added to a SQLite outbox with a unique event ID, retried after
reconnection, and removed only after PUBACK. The outbox keeps the latest 1,000
snapshots (about 3.5 days at a five-minute interval); it is a bounded telemetry
buffer, not a complete off-device backup. Oldest unsent snapshots may be dropped
when full. Local readings remain under the configured retention policy.

QoS 1 can deliver duplicates. A future AWS consumer must deduplicate by `event_id`.
Telemetry carries mode, timestamp, device identity, fault/armed state, and the two
plant readings. It excludes passwords, sessions, certificates, and private keys.
The dashboard reports disabled/connecting/offline/connected and pending messages.

IoT Rules, Lambda, long-term storage, notifications, Cognito, and Device Shadows
are future optional increments. Their cost and deployment are outside this local
delivery. Use AWS Budgets alerts when provisioning; alerts are not spending caps.

Official references: [AWS IoT MQTT](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html),
[X.509 authentication](https://docs.aws.amazon.com/iot/latest/developerguide/x509-client-certs.html),
[pricing](https://aws.amazon.com/iot-core/pricing/), and
[Paho client API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
