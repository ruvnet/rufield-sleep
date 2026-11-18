# Connect the room

Use separate sensing and audio boards. A loopback host runs the viewer and the management console. A small Linux computer or an existing Mac can host both.

| Equipment | Purpose |
| :--- | :--- |
| ESP32 CSI node supported by RuView, for example an ESP32 S3 | Send room observations to the existing RuView sensing pipeline |
| ESP32 S3 development board and USB data cable | Receive speaker commands over serial |
| MAX98357A I2S amplifier, matching speaker and a mute button | Convert digital samples to sound with local control |

## Sensor feed

1. Follow the [RuView node guide](https://github.com/ruvnet/RuView/tree/main/firmware/esp32-csi-node) to provision the CSI sensor and connect it to a RuView host that publishes signed FieldEvents. Scope the upstream to **one bedroom**. The viewer removes device and zone identifiers from its public projection.
2. Enroll the sensor's independently obtained public key in the [RuField viewer](https://github.com/ruvnet/rufield/tree/82ffc267617c59b91d32f7fcfc77896988fd0012/crates/rufield-viewer). Use the live viewer with production trust. The following example assumes your RuView endpoint is available locally on port 8080. Substitute the upstream port, sensor ID and enrolled public key for your installation.

    ```sh
    cargo run --locked -p rufield-viewer -- --source live \
      --upstream http://127.0.0.1:8080 --trust-mode production \
      --sensor-key "$SENSOR_ID=$PUBLIC_KEY_HEX"
    ```

3. In another terminal, start this console. The default viewer port is 8088. Select **Connect feed**. A live label needs fresh frames from a production viewer. If your RuView deployment requires credentials, configure access on the viewer side. The console accepts only a loopback viewer port.
4. To exercise the integration without a node, run `cargo run --locked -p rufield-viewer` in the RuField checkout. Select **Connect feed**. Expect **Synthetic**. The speaker guard stays unavailable in this mode.

## Speaker

Example pin map for a dedicated S3 development board. Check your board schematic for reserved pins. Use the amplifier module's specified supply, speaker impedance and output wiring.

| S3 | Connection |
| :--- | :--- |
| GPIO 4 | Amplifier BCLK |
| GPIO 5 | Amplifier LRC / WS |
| GPIO 6 | Amplifier DIN |
| GND | Amplifier ground |
| GPIO 7 | Normally open mute button to GND |
| USB | Host USB serial connection |

Connect the speaker across the module's differential speaker outputs. Firmware sends the same samples to both I2S slots. The level control sets digital amplitude. Physical loudness depends on the amplifier, speaker and distance. Set the amplifier to its lowest practical gain and check it while awake.

Install Arduino CLI, then use the following from this repository. Set PORT to your board. Use the USB CDC port on a supported S3 board, or select the matching UART settings for a board with a USB serial bridge.

```sh
PORT=/dev/ttyACM0
INDEX=https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index --additional-urls "$INDEX"
arduino-cli core install esp32:esp32@3.3.2 --additional-urls "$INDEX"
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/sleep_speaker
arduino-cli upload -p "$PORT" --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/sleep_speaker
python3 app.py --speaker "$PORT"
```

Select **Connect USB**, set a one minute timer and level 1, then select **Play routine**. Use **Stop** or the physical mute button to end playback. The console owns the session timer, so closing the browser leaves a running session under the server's control. Restarting the host or losing the serial link lets the board's three second lease expire. The board also enforces a 30 minute maximum per start.

## Bench acceptance

With a real amplifier attached, verify silence on power up, audible low level playback, UI stop, physical mute and timer expiry. Keep the board powered from a separate supported supply while removing the serial link to verify that the output stops within three seconds plus buffered audio. Repeat with a production sensor feed: disconnect the feed and confirm the guarded routine ends without restarting. Record board revision, speaker, measured loudness at the pillow and observed stop latency. The current software tests cannot measure any of these physical properties.

[Espressif Arduino I2S documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html)
