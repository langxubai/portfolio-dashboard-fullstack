# iOS 小组件桌面看板 (Finance Board Widget)

通过 iOS 应用 [Scriptable](https://scriptable.app/)，我们能在 iPhone 的主屏幕上构建原生的自定义小组件，本目录包含了供您使用的自定义桌面资产看板源码。

## 安装步骤 (Setup Instructions)

1. **下载 App**：前往 iOS 的 App Store 下载并安装 [Scriptable](https://apps.apple.com/us/app/scriptable/id1405459188)（这是一款免费并且功能极强的 JavaScript 运行环境 App）。

2. **新建 Script**：打开 Scriptable，点击右上角的 `+` 新建一个脚本文件，并将本目录下的 `FinanceBoardWidget.js` 文件的所有内容复制并粘贴到 Scriptable 的编辑器中。重命名该脚本为 "Finance Board" 等你喜欢的名字。

3. **配置网络与接口 (BACKEND_URL)**：
   > [!IMPORTANT]
   > 桌面组件的请求由你的 iPhone 发起，而不是你的电脑。因此它**无法**连接 `http://127.0.0.1:8000` 或 `localhost`。并且后端服务被启动时，**必须监听外网访问**才行。
   
   在启动后端服务时，请务必使用如下命令，使得所有网卡的请求都能被接收：
   ```bash
   uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   接下来，你需要将组件的代码里的 `BACKEND_URL` 改成可访问该后端的 IP 地址：

   * **方案 A：基于同一个局域网 (Wi-Fi)**
     - 打开您的 Mac，进入 **系统设置** -> **网络** -> **Wi-Fi** -> **高级**。记录您的「IP 地址」，如 `192.168.1.100`。
     - 确保 iPhone 与 Mac 连在同一 Wi-Fi。填写 `const BACKEND_URL = "http://192.168.1.100:8000"`。

   * **方案 B：基于虚拟局域网 (例如 Tailscale / ZeroTier)**
     - 打开 Tailscale 找到你 Mac 的节点专属 IP（通常是 `100.x.x.x` 开头）。
     - 确保 iPhone 此时也打开并连上了 Tailscale VPN。
     - 填写 `const BACKEND_URL = "http://100.x.x.x:8000"`。使用这种方案即使你出门没连 Wi-Fi 也能同步看盘数据！

   如果在未来你将后端应用部署到了云端（例如使用 Render，Railway），则只需填入对应的线上地址即可。

4. **测试脚本**：在 Scriptable 的脚本编辑界面，点击右下角的 `▶`（运行按钮）。它会在应用内展示出一个“看板”的预览UI并模拟发送请求，如果报错，请检查终端日志或你的 `BACKEND_URL` 是否连通。

5. **添加到主屏幕**：
   - 返回 iPhone 主屏幕，长按空白处进入编辑模式 (Jiggle mode)。
   - 点击左上角的 `+` 按钮，向下滚动找到 **Scriptable**。
   - 寻找合适的尺寸（本组件在 "小尺寸 (Small)" 及 "中尺寸 (Medium)" 上均效果良好），点击 **添加小组件**。
   - 回到桌面，点击新建的小组件，在弹出的菜单中的 "Script" 项里选择刚才创建的 "Finance Board"，完成设置。

## 功能延展 (Future Expansion)

我们在组件代码内部已经预留好了 `TODO [Future Expansion Interface]: Add daily_pnl calculation`。当后续后端 `/api/positions` 能够通过比对昨日收盘价输出单日涨跌幅和数值时，只需修改两行被注释的代码即可将其显示于界面上。
