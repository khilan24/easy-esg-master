# 阿里云服务器部署说明

本文档说明如何将本项目部署到阿里云 ECS，并通过公开域名访问。版本控制使用 GitHub，后续迭代通过 `git pull` + 重启服务完成。

---

## 项目架构简述（与部署相关）

- **入口**：用户通过浏览器访问 Web 前端（Flask 提供 `web/app.py` + `templates/index.html`）。
- **API Key**：前端页面提供模型选择（Gemini / 千问）与 **API Key 输入框**；用户填写后点击「生成报告」，前端通过 POST `/api/run` 将 `api_key` / `api_keys` 传给后端。
- **后端**：Flask 收到请求后，将 Key 注入环境变量（`ESG_RUNTIME_API_KEY`、`ESG_RUNTIME_API_KEY_E/S/G`），再以子进程方式启动 `main.py`；`main.py` 内 `load_config()` 优先从环境变量读取 Key，**无 config.json 也可正常运行**。
- **流程**：`main.py` 调用 `core/research_stages.py` 的 ResearchPipeline，依次执行 E/S/G 深度研究 → 润色 → 热点聚焦 → 合并 → Word 与 PPT 填充；结果写入 `output/<job_id>/weekly|daily/`，前端轮询 `/api/status` 展示进度与日志，并提供下载。
- **结论**：部署时**无需**在服务器上创建 `config.json`；用户在前端输入 API Key 即可。仅当需要服务端默认 Key 或默认模型时可选用 config.json。

---

## 一、部署前准备清单

### 已确定信息（可直接使用）

| 项目 | 值 |
|------|-----|
| **GitHub 仓库** | https://github.com/khilan24/easy-esg-master |
| **分支** | `main` |
| **公网 IP** | 139.196.89.245 |
| **操作系统** | Ubuntu 24.04（与下文命令兼容） |

### 其他需要提供/决定的信息（见下方逐项说明）

| 类别 | 需要准备/决定的内容 |
|------|---------------------|
| **GitHub** | 仓库类型（公开/私有）；分支一般为 `main`，已满足 |
| **阿里云 ECS** | SSH 登录方式（密码或密钥） |
| **部署路径** | 服务器上项目目录（建议直接用 `/home/esg/easy-esg`） |
| **运行用户** | 用于运行应用的系统用户（建议直接用 `esg`） |
| **域名** | 用于访问的域名；**若无域名可暂用 IP**：http://139.196.89.245:8080 |
| **API Key** | **无需在服务器配置**：网站前端已包含 API Key 输入框，用户访问页面时填写即可 |

---

## 接下来你需要做的工作（按顺序）

1. **阿里云控制台**  
   - 登录 [阿里云 ECS 控制台](https://ecs.console.aliyun.com)，找到实例 **139.196.89.245**。  
   - 进入该实例的 **安全组**，放行入方向：**22**（SSH）、**8080**（ESG Web）。

2. **本机 SSH 登录 ECS**  
   - 在本地终端执行：`ssh root@139.196.89.245`  
   - 首次连接时提示 `Are you sure you want to continue connecting?` 输入 **yes**（完整拼写）。  
   - 出现 `password:` 时输入实例的 root 密码（在控制台「重置实例密码」可查看/修改），输入时屏幕不显示，输完回车即可。

3. **在服务器上执行部署命令**（登录成功后，在 ECS 上按顺序执行）  
   - **3.1 安装依赖**：见下文「三、服务器环境」的 3.1。  
   - **3.2 创建用户 esg**：见 3.2。  
   - **3.3 克隆项目并创建虚拟环境**：见 3.3（仓库公开，直接 clone 即可）。  
   - **跳过 3.4**：无需配置 config.json，用户在前端填 API Key。  
   - **3.5 测试运行**：见 3.5，确认 gunicorn 能跑。  
   - **四、配置 systemd**：安装并启用 esg-app 服务（**必须完成此项，应用才会一直运行**，否则 3.5 测试结束后进程会退出）。
   - **五、配置 Nginx**：复制 `deploy/nginx/esg.conf` 到 sites-available，启用并重载 Nginx。

4. **验证**  
   - 在浏览器打开 **http://139.196.89.245:8080**，应能看到 ESG 工具页面；选择模型、填写 API Key 后点击「生成报告」即可使用。

5. **后续更新**  
   - 代码更新后，在服务器上进入 `/home/esg/easy-esg`，执行 `./deploy/scripts/update.sh`（或按「七、后续版本迭代」手动执行）。

---

## 一（续）、各项信息说明与在哪里找到

- **仓库类型（公开/私有）**  
  - **含义**：你的 GitHub 仓库是否对所有人可见。  
  - **在哪里看**：打开 https://github.com/khilan24/easy-esg-master ，仓库名下方若显示 **Public** 即为公开，**Private** 即为私有。  
  - **影响**：公开仓库在服务器上直接 `git clone` 即可；私有仓库需要在服务器上配置 SSH 密钥或 Personal Access Token 才能拉取（见文末「私有仓库」小节）。

- **SSH 登录方式（密码 或 密钥）**  
  - **含义**：你用什么方式登录 ECS（在本地电脑用「终端」或「PowerShell」输入 `ssh root@139.196.89.245` 时，是输入密码还是用密钥文件）。  
  - **在哪里找**：  
    - 阿里云控制台 → **云服务器 ECS** → **实例与镜像** → **实例** → 点进你的实例 → **远程连接**（或 **更多** → **密码/密钥**）。  
    - 若当时选择的是「密钥对」：在本地会有一个 `.pem` 文件，登录命令形如：`ssh -i 你的密钥.pem root@139.196.89.245`。  
    - 若选择的是「密码」：实例详情里可重置实例密码，登录时输入该密码即可。  
  - **部署时**：只要你能用 `ssh root@139.196.89.245`（或 `ssh -i xxx.pem root@139.196.89.245`）成功登录，就可以按文档在服务器上执行命令，无需额外“提供”这项给文档，只是要确保安全组已放行 22 端口。

- **部署路径**  
  - **含义**：在服务器上把代码克隆到哪个目录，例如 `/home/esg/easy-esg` 表示「用户 esg 的家目录下的 easy-esg 文件夹」。  
  - **如何决定**：不需要在别处“找”，你**自己定一个目录**即可。建议直接用 **`/home/esg/easy-esg`**，这样和文档里的命令一致，复制粘贴即可。若你改成别的路径，后续所有出现 `/home/esg/easy-esg` 的地方都要一起改。

- **运行用户**  
  - **含义**：用哪个系统用户来运行 gunicorn（跑网站进程）。不用 root 更安全，所以建议单独建一个用户。  
  - **如何决定**：不需要在别处“找”，你**自己定一个用户名**即可。建议直接用 **`esg`**，文档里会教你在服务器上执行 `useradd` 创建这个用户；若你用别的名字，把文档里所有 `esg` 替换成该用户名即可。

- **域名**  
  - **含义**：是否用类似 `esg.xxx.com` 这样的地址访问，而不是用 IP `http://139.196.89.245`。  
  - **在哪里配置**：  
    - 若**没有域名**：可以不填，直接用 **http://139.196.89.245** 访问；Nginx 配置里用 `server_name _;` 即可（见第五节）。  
    - 若**有域名**：在购买域名的服务商控制台（阿里云万网、腾讯云 DNSPod 等）里，添加一条 **A 记录**，主机记录填 `@` 或 `www`，记录值填 **139.196.89.245**，这样域名就会解析到你这台 ECS。  
  - **备案**：域名若在中国大陆且用国内 ECS，需在阿里云备案中心完成 ICP 备案后才能用域名访问；仅用 IP 访问则不需要备案。

- **API Key（无需在服务器配置）**  
  - **说明**：本项目的 **Web 前端已包含 API Key 输入窗口**。用户打开部署后的网站（如 http://139.196.89.245:8080），在页面上选择模型（Gemini 或千问）并填写对应 API Key，点击「生成报告」即可，**无需在服务器上创建或填写 config.json**。后端会通过请求体接收前端传入的 Key，并注入到运行环境中供主流程使用。  
  - **可选**：若你希望设置**默认模型**或**服务端默认 Key**（例如不希望在页面暴露 Key、仅内网使用），可在服务器上按「3.4 配置 config.json（可选）」创建 `config.json`；此时前端仍可覆盖该配置。Key 来源：Gemini 在 Google AI Studio，千问在阿里云 DashScope/灵积控制台。

---

## 二、阿里云控制台准备

1. **安全组**：放行 **22**（SSH）、**8080**（ESG Web）。
2. **域名解析**（可选）：若有域名，在域名服务商处添加 **A 记录**，将域名指向 ECS 公网 IP；访问时使用 `http://域名:8080`。
3. **备案**：若使用中国大陆 ECS 且通过域名访问，需完成 ICP 备案。

---

## 三、服务器环境（首次部署）

以下以 **Ubuntu 24.04** 为例（与 Ubuntu 22.04 命令一致），使用 `root` 或具备 sudo 权限的账号 SSH 登录后执行。登录示例：`ssh root@139.196.89.245`（若使用密钥：`ssh -i 你的密钥.pem root@139.196.89.245`）。

**说明**：本节只完成环境安装与一次性的「测试运行」；测试时 gunicorn 在前台运行，断开 SSH 或按 Ctrl+C 即停止。要让项目**一直在服务器上运行**，必须继续完成 **第四节（systemd）** 和 **第五节（Nginx）**。

### 3.1 安装依赖

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx
```

### 3.2 创建运行用户（推荐）

```bash
sudo useradd -m -s /bin/bash esg
```

若使用其他用户名，请记下，后续在 systemd 和脚本中统一替换 `esg`。

### 3.3 克隆项目并创建虚拟环境

以下使用仓库 **https://github.com/khilan24/easy-esg-master** 与项目目录 **/home/esg/easy-esg**；若你改用其他路径或用户，请同步修改后续命令中的路径与用户。

```bash
sudo -u esg git clone https://github.com/khilan24/easy-esg-master.git /home/esg/easy-esg
cd /home/esg/easy-esg

sudo -u esg bash -c 'cd /home/esg/easy-esg && python3 -m venv venv'
sudo -u esg /home/esg/easy-esg/venv/bin/pip install -r requirements.txt
sudo -u esg /home/esg/easy-esg/venv/bin/pip install gunicorn
```

**私有仓库**：若该仓库为 Private，需在服务器上配置 SSH key 或 Personal Access Token 后再 `git clone`（见文末「私有仓库」小节）。

### 3.4 配置 config.json（可选）

**默认无需执行**：用户在前端页面填写 API Key 即可。仅当需要服务端默认模型或默认 Key 时，在服务器上创建 `config.json`：

```bash
sudo -u esg cp /home/esg/easy-esg/config/config.json.example /home/esg/easy-esg/config.json
sudo -u esg nano /home/esg/easy-esg/config.json
```

按需填写 `provider`、`gemini` / `qwen` 的 `api_key` 等（参考项目根目录 `README.md`）。**不要**将含真实 Key 的 config 提交到 GitHub。

### 3.5 测试运行

```bash
sudo -u esg /home/esg/easy-esg/venv/bin/gunicorn -w 1 -b 127.0.0.1:5000 web.app:app
```

另开一个终端执行 `curl http://127.0.0.1:5000`，能返回页面即正常。用 `Ctrl+C` 停止测试。

---

## 四、配置 systemd 服务（开机自启、崩溃自拉）

1. 若 **项目目录** 或 **运行用户** 与示例（`/home/esg/easy-esg`、`esg`）不同，请编辑 `deploy/systemd/esg-app.service`，将所有 `/home/esg/easy-esg` 改为实际项目路径、`esg` 改为实际运行用户。

2. 安装并启用服务：

   ```bash
   cd /home/esg/easy-esg
   sudo cp deploy/systemd/esg-app.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable esg-app
   sudo systemctl start esg-app
   sudo systemctl status esg-app
   ```

3. 查看日志：`sudo journalctl -u esg-app -f`

---

## 五、配置 Nginx 反向代理（8080 端口）

```bash
cd /home/esg/easy-esg
sudo cp deploy/nginx/esg.conf /etc/nginx/sites-available/esg
sudo ln -sf /etc/nginx/sites-available/esg /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

完成后通过 **http://139.196.89.245:8080** 访问。

---

## 六、HTTPS（可选）

若已配置域名且 8080 可访问，可申请免费证书（需在 Nginx 中为 8080 配置域名后使用 certbot）。

---

## 七、后续版本迭代（更新流程）

### 方式一：使用更新脚本（推荐）

在服务器项目目录下执行（需对 `deploy/scripts/update.sh` 有执行权限）：

```bash
cd /home/esg/easy-esg
chmod +x deploy/scripts/update.sh
./deploy/scripts/update.sh
```

脚本会执行：`git pull` → 安装依赖 → `sudo systemctl restart esg-app`。

### 方式二：手动更新

```bash
cd /home/esg/easy-esg
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart esg-app
```

---

## 八、私有 GitHub 仓库

若仓库为**私有**，服务器上需能拉取代码，任选其一：

- **SSH 密钥**：在服务器上生成 SSH key，将公钥添加到 GitHub 仓库的 Deploy keys 或账号 SSH keys，clone 时使用 `git@github.com:用户名/easy-esg-master.git`。
- **Personal Access Token（HTTPS）**：在 GitHub 创建带 `repo` 权限的 Token，clone 时使用：
  `https://<TOKEN>@github.com/用户名/easy-esg-master.git`，或配置 Git 凭据存储。

---

## 九、文件说明

| 路径 | 说明 |
|------|------|
| `deploy/systemd/esg-app.service` | systemd 服务单元模板，需替换项目目录与运行用户后复制到 `/etc/systemd/system/` |
| `deploy/nginx/esg.conf` | Nginx 配置（8080 端口），安全组需放行 8080 |
| `deploy/scripts/update.sh` | 服务器端一键更新脚本（git pull + 安装依赖 + 重启服务） |

---

## 十、注意事项

- **API Key**：由用户在前端页面填写，无需在服务器上创建 config.json；若你已创建 config.json，其在 `.gitignore` 中，不会随 `git pull` 被覆盖。
- **output** 目录为报告输出，也在 `.gitignore` 中；若需保留历史报告，可在服务器上定期备份。
- 若修改了 **项目目录** 或 **运行用户**，需同步修改 `deploy/systemd/esg-app.service` 并重新 `sudo cp` 与 `daemon-reload`。
