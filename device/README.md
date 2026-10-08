# ATOM Matrix 韌體

ESP32-PICO-D4、4 MB flash、MicroPython v1.26.1。LED GPIO27；按鈕 GPIO39。此台已確認使用 BMI270：I2C 位址 0x68、SCL21、SDA25。

上電立即顯示藍色。收到 USB 狀態後播放指定動畫並循環，直到下一個指令或按鈕操作。按鈕依序切換綠→黃→紅→藍；長按不連跳。四方向重力旋轉保留，平放時維持上次方向。

- 綠色：逐筆畫勾，約 0.84 秒畫完，完整亮著至第 6 秒，再用 1 秒平滑淡出；7 秒一輪。
- 黃色：每列約 300ms 的慢速寬瀑布，2.1 秒無縫循環。
- 紅色：全暗→中心→實心 3×3→全板（停留較久）→實心 3×3→中心→全暗，以較慢的餘弦亮度曲線像呼吸般向外擴散再收回；4.2 秒一輪。
- 藍色：連續水波，依自然波形週期無縫流動（4.2 秒），沒有固定 5 秒淡出或重播停頓。

## 更新程式

以下從專案根目錄執行；先關閉占用 COM3 的 controller。若埠號不同，替換 COM3。

```powershell
& .\.venv\Scripts\python.exe -m mpremote connect COM3 fs cp device\device_protocol.py :device_protocol.py
& .\.venv\Scripts\python.exe -m mpremote connect COM3 fs cp device\orientation.py :orientation.py
& .\.venv\Scripts\python.exe -m mpremote connect COM3 fs cp device\bmi270_config.bin :bmi270_config.bin
& .\.venv\Scripts\python.exe -m mpremote connect COM3 fs cp device\main.py :main.py
& .\.venv\Scripts\python.exe -m mpremote connect COM3 reset
```

本機維護工具需要 `pip install esptool mpremote`。第一次安裝 MicroPython，先執行以下兩行（會清除裝置檔案），再執行上面的更新指令：

```powershell
& .\.venv\Scripts\python.exe device\flash_tool.py --port COM3 --baud 115200 erase-flash
& .\.venv\Scripts\python.exe device\flash_tool.py --port COM3 --baud 115200 write-flash 0x1000 device\firmware\ESP32_GENERIC-20250911-v1.26.1.bin
```

## 協定

115200 baud、8N1、逐行 ASCII JSON，每行最多 256 字元。ID 為 1–40 字元字串。

```json
{"id":"abc","op":"set","state":"running"}
{"id":"abc","op":"get"}
{"id":"abc","op":"identify"}
```

三種命令均回覆帶同一 ID 的 `{"id":"abc","ok":true,"state":"running","device":"m5stack-matrix-agent","protocol":1}`。非法命令不改變狀態。`get` 與 `identify` 不會重啟動畫。接收採非阻塞解析；同一 UART 也會有啟動與方向紀錄。保留 Ctrl-C 供 mpremote 維護，不要傳送任意二進位資料。

## 驗證與來源

`python device/verify_animation.py` 檢查動畫、綠色停留及銜接、黃色無縫循環、旋轉與防抖。`python device/observe.py` 在重啟後擷取 24 秒啟動／循環紀錄至 `device/firmware/runtime.log`。

初次燒錄以 115200 baud 通過 esptool hash 校驗。原韌體完整備份未成功；`backup/probe.bin` 只有開頭 64 KB，不能用來完整還原。`backup/main-v1.py` 是舊動畫原始碼。

官方參考：[M5Stack Matrix](https://docs.m5stack.com/en/core/ATOM%20Matrix)、[MicroPython ESP32](https://micropython.org/download/ESP32_GENERIC/)。

`bmi270_config.bin` 取自 [Bosch BMI270 SensorAPI](https://github.com/boschsensortec/BMI270_SensorAPI/blob/master/bmi270.c) 的 8192-byte 陣列；原始碼及授權在 `vendor`。SHA256：`2d75e68e343a13ff99be98261dfbd99d9e8c6f267da9e3c5aeb883276ad178db`。軸向參考 [M5Unified](https://github.com/m5stack/M5Unified/blob/master/src/utility/IMU_Class.inl)。
