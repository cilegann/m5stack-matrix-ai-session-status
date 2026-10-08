# M5Stack Matrix agent 狀態燈

專案分為兩部分：

- `control/`：電腦端 Python USB 控制模組、自動 COM 偵測、測試與使用說明。
- `device/`：裝置 MicroPython 程式、動畫、重力感應、USB 協定、燒錄工具及韌體檔。

`.venv/` 是本機開發環境，不需複製給裝置。

## 快速使用

```powershell
python -m pip install -r control/requirements-control.txt
```

從專案根目錄，或將 `control` 資料夾複製到另一個 Python 專案：

```python
from control import set_state, MatrixController

set_state('done')  # 自動偵測 COM，顯示綠色勾勾

with MatrixController() as matrix:
    matrix.set_state('running')
    print(matrix.get_state())
    print(matrix.get_connect_state())  # 'COM3' 或 'disconnect'
    matrix.reconnect()                # 主動重連；set_state/get_state 也有自動恢復
```

支援 `done`（綠）、`running`（黃）、`attention`（紅）、`idle`（藍）。可用 `port='COM3'` 明確指定裝置。偵測以 USB VID/PID 篩選並查詢韌體身分；多台裝置時不自動選擇。

裝置上電預設藍色，收到狀態後循環對應動畫。相同狀態滿 1 小時會熄燈休眠；休眠期間收到不同的 USB 狀態會立即喚醒並重新計時，相同狀態則維持熄燈。按一下本體按鈕也可立即休眠，再按一下會以目前正確狀態喚醒。重力旋轉仍可使用。綠色畫完後維持約 5 秒，再淡出重畫；黃色保持慢速無縫水流。

詳細說明：[控制端](control/README.md)、[裝置端與燒錄](device/README.md)。

## 驗證

```powershell
& .\.venv\Scripts\python.exe control\test_control.py
& .\.venv\Scripts\python.exe device\verify_animation.py
```

實機重啟後可執行 `control/verify_usb.py`，驗證自動偵測、開機藍色、四種狀態與傳輸恢復。
