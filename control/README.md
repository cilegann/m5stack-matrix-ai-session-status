
# Python USB 控制端

在使用控制端的 Python 環境安裝 `python -m pip install -r control/requirements-control.txt`。

從專案根目錄，或把整個 `control` 資料夾放進你的 Python 專案：

```python
from control import set_state, MatrixController, detect_port

set_state('running')  # 自動偵測 USB COM port，等裝置確認後回傳 'running'
set_state('attention')
set_state('done')
set_state('idle')

print(detect_port())  # 例如 COM3；只查詢身分，不切換動畫

with MatrixController() as matrix:  # 頻繁更新時推薦保持連線
    print(matrix.port)
    matrix.set_state('running')
    print(matrix.get_state())
    matrix.set_state('done')
```

## 斷線恢復與連線狀態

```python
from control import MatrixController

with MatrixController(timeout=5, reconnect_timeout=5) as matrix:
    print(matrix.get_connect_state())  # 'COM3' 或 'disconnect'
    matrix.set_state('running')        # 通訊失敗時自動重連並重送一次
    port = matrix.reconnect()          # 主動關閉舊連線、重新連線並確認韌體
    print(port)                       # 例如 'COM3'
```

- `set_state()`、`get_state()` 遇到 USB 錯誤或回覆逾時，會嘗試重連，再重送這次請求一次；不在背景無限重試。裝置明確拒絕命令時不重試。
- 未指定 `port` 時，重連會重新偵測，因此能處理 COM 編號改變；明確指定 `COM3` 時只重試 COM3。多台符合裝置時仍不會隨意選擇。
- `reconnect()` 成功回傳埠名，失敗拋出 `TimeoutError`。`reconnect_timeout` 是這一輪重連的時間預算（預設 5 秒）；命令本身仍有 `timeout` 的傳送／回覆等候時間。底層作業系統開關埠的耗時另計。
- `get_connect_state(timeout=0.5)` 以韌體身分查詢實測目前連線，不只檢查本機 serial handle。失敗回傳字串 `'disconnect'` 並關閉失效連線；這個函式本身不觸發重連、不改動畫。
- 重連失敗後物件仍可使用：USB 回來後，再呼叫 `set_state()` 或 `reconnect()` 即可。單獨 `reconnect()` 不重送舊狀態；自動重連會重送當次請求。
- 呼叫 `close()` 後不會由 `set_state()` 自動打開，避免結束連線後意外操作裝置；若要重用，明確呼叫 `reconnect()`。
- 建構 `MatrixController()` 時仍需要裝置可連線；若尚未插入，建構會失敗。自動恢復適用於已成功建立的物件。

也可以只複製 `matrix_control.py`，使用 `from matrix_control import set_state`。

| 狀態 | 顏色／意義 |
| --- | --- |
| `done` | 綠色：全部完成 |
| `running` | 黃色：全部執行中 |
| `attention` | 紅色：需要接手 |
| `idle` | 藍色：無 session／開機預設 |

## 自動偵測

省略 `port` 或傳入 `None` 時，篩選此 ATOM Matrix 的 FTDI USB 橋接器（VID 0403、PID 6001），逐一發送只讀 `identify`，確認韌體的 `device=m5stack-matrix-agent` 與 `protocol=1`。不會只依 COM 編號或第一個 USB 裝置做選擇。需使用本專案新版韌體。

找到多台、沒有相符裝置，或裝置被其他程式占用時會拋出 `RuntimeError`。每個候選裝置預設在 3 秒內重試身分查詢，涵蓋一般啟動時間；若剛上電尚未準備完成，可稍後重試，或先呼叫 `detect_port(timeout=5)`。

仍可指定埠：`set_state('done', port='COM3')` 或 `MatrixController('COM3')`。其他 USB 橋接器型號也可用明確指定的埠連接。

## 行為與例外

- import 不開啟 USB。單次 `set_state` 自動開關連線；持續控制建議重用 `MatrixController`，免去重複偵測。
- 相同狀態重送不重啟動畫；關閉連線保留最後狀態；裝置重新上電回到藍色。
- 保留裝置按鈕切換與重力旋轉。按鈕操作後，可用 `get_state()` 讀取實際模式。
- 無效狀態拋出 `ValueError`；重連或重送仍未取得確認時可能拋出 `TimeoutError`，此時狀態可能已改變，可稍後查詢。
- 建構或重送時 USB 失敗可能拋出 `serial.SerialException`；裝置拒絕命令拋出 `RuntimeError`。
- 同一 controller 的呼叫有執行緒鎖；同一埠只由一個程式占用。燒錄前先 `close()` 或離開 `with`。

單元測試：`python control/test_control.py`。實機測試：裝置重啟且尚未切換狀態時，執行 `python control/verify_usb.py`；測試最後設回藍色。

2026-10-08：14 項單元測試通過，包含 COM 編號變更、重連逾時、失效 handle、ACK 遺失與主動 close。COM3 實機以關閉 handle 模擬連線失效，驗證同一物件自動恢復、主動重連及狀態查詢；未做實體拔插測試。
