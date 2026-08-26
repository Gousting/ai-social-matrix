# AI社交媒体矩阵管理运营系统

> **版本**：v1.5  
> **定位**：国内平台 · 单号起步逐步扩张 · 图文为主可扩展视频 · 本地部署 · 低成本方案  
> **垂类**：AI工具教程（Codex / MiniMax / 各类AI开源项目安装使用）

## 项目简介

一套**低成本、本地部署、AI辅助**的社交媒体内容运营工具，采用"先跑通再复制"的策略，验证AI辅助内容运营的道路可行性。

### 核心策略

- **先跑通再复制**：没沉淀出爆款模板库之前不开新号；私域没跑通第一单之前不扩矩阵
- **单号极致垂直**：第1个月只做1个小红书号，前15篇只打一个标签，日更
- **AI辅助非AI替代**：AI只负责出初稿，人工必须深度修改（修改率≥60%）
- **合规优先**：主动标识AI内容，禁止私域引流违禁词，发布时间随机化

## 3个月运营节奏

| 阶段 | 时间 | 账号 | 核心动作 | 退出标准 |
|---|---|---|---|---|
| **冷启动** | 第1个月 | 1个小红书主号 | 极致垂直，前15篇只打一个标签，日更 | 粉丝≥500，1篇互动>200，沉淀3个爆款模板 |
| **模型验证** | 第2个月 | +抖音分发号 | 同素材改编（剪映AI图文成片），建私域SOP，跑通第一单 | 主号≥1000粉，私域≥100人，跑通第一单 |
| **矩阵验证** | 第3个月 | +第2个小红书号 | 同人设换切片，验证爆款模型可复制性 | 3个号稳定运行，月曝光≥10万，月收入≥500元 |

## 项目结构

```
ai-social-matrix/
├── config/                    # 配置文件
│   ├── accounts.yaml          # 账号配置（单号起步，逐步扩张）
│   ├── api_keys.yaml          # API Key配置（多服务商轮询）
│   └── settings.yaml          # 系统设置（排期/改写/合规检查）
├── scripts/                   # 核心脚本
│   ├── utils/                 # 工具模块
│   │   ├── config_loader.py   # 配置加载器
│   │   ├── db.py              # 数据库管理
│   │   ├── api_client.py      # LLM API客户端（多Key轮询）
│   │   ├── clash_client.py    # Clash代理客户端
│   │   └── logger.py          # 日志模块
│   ├── publishers/            # 平台发布器
│   │   ├── base.py            # 基础发布器抽象类
│   │   └── xiaohongshu.py     # 小红书发布器
│   ├── 01_collect_topics.py   # 选题采集
│   ├── 02_ai_rewrite.py       # AI内容改写（含合规检查+AI标识）
│   ├── 03_image_process.py    # 图片处理（裁剪/水印/封面）
│   ├── 04_schedule.py         # 排期发布引擎（含时间随机化）
│   ├── 05_compliance_check.py # 合规检查（v1.5新增）
│   ├── login_account.py       # 账号登录绑定
│   └── test_phase1.py         # Phase1综合测试
├── data/                      # 数据目录
│   ├── raw_notes/             # 原始选题
│   ├── drafted/               # 草稿（待审核/已审核）
│   ├── metrics/               # 数据指标
│   └── reports/               # 复盘报告
├── docs/                      # 文档
│   └── AI社交媒体矩阵管理运营系统实施方案书_v1.5.md
├── images/                    # 图片资源
├── requirements.txt           # Python依赖
└── .gitignore                 # Git忽略配置
```

## 快速开始

### 1. 环境准备

```bash
# 安装Python依赖
pip install -r requirements.txt

# 安装Playwright浏览器
python -m playwright install chromium
```

### 2. 配置API Key

编辑 `config/api_keys.yaml`，配置免费LLM API（支持多服务商轮询）：

```yaml
providers:
  opencode:
    enabled: true
    base_url: "https://opencode.ai/zen/v1"
    api_key: "your-api-key"
    model: "x-preview-f-free"
    extra_headers:
      x-preview-f-free: "true"
```

### 3. 配置账号

编辑 `config/accounts.yaml`，第1个月只启用1个小红书主号：

```yaml
accounts:
  - platform: xiaohongshu
    name: ai_main
    enabled: true
    stage: 1
    use_proxy: false  # 主号用住宅IP或手机流量，不用Clash机房IP
    focus_tag: "Codex安装使用"  # 前15篇统一标签
    warmup_days: 7  # 7天养号期
```

### 4. 登录账号

```bash
# 列出所有账号
python scripts/login_account.py --list

# 登录指定账号（扫码登录）
python scripts/login_account.py --login ai_main
```

### 5. 内容生产流程

```bash
# Step1: 采集选题
python scripts/01_collect_topics.py --generate-sample

# Step2: AI改写（自动添加AI标识+合规检查）
python scripts/02_ai_rewrite.py --top 5 --platform xiaohongshu

# Step3: 合规检查（v1.5新增，发布前必做）
python scripts/05_compliance_check.py

# Step4: 图片处理
python scripts/03_image_process.py --input ./images/source --output ./images/processed

# Step5: 排期发布（时间自动随机化±30分钟）
python scripts/04_schedule.py --schedule
python scripts/04_schedule.py --publish-all --dry-run  # 先试运行
python scripts/04_schedule.py --publish-all             # 实际发布
```

## v1.5 重要更新（基于可行性检查）

### 修正的3个严重缺陷

1. **私域引流合规化**：去掉"评论区扣1"（违规），改用平台官方留资组件/群聊/瞬间/置顶笔记引导
2. **人工修改率提升**：从≤50%提升到≥60%，2026年平台要求AI产出后手动改60%以上才合规
3. **抖音分发改用剪映AI**：用抖音官方剪映AI图文成片（全免费，流量适配好），不自己写脚本

### 新增功能

- **AI内容自动标识**：改写时自动在正文添加"人工智能生成，已人工审核优化"
- **合规检查脚本**：`05_compliance_check.py`，检测私域引流违禁词、广告法违禁词、AI标识
- **发布时间随机化**：排期时自动±30分钟浮动，避免太规律被判定为机器发布
- **7天养号期**：新号前7天只浏览不发布，第8天开始发布

### 2026年平台合规要求

| 要求 | 说明 | 处罚 |
|---|---|---|
| 主动标识AI内容 | 发布时勾选"AI合成内容"，正文标注"人工智能生成" | 首次漏标限流7天，二次禁言30天，三次永久封禁 |
| 人工修改率≥60% | AI产出后必须人工深度修改，搭配真实拍摄素材 | 纯AI内容直接限流，账号权重降级 |
| 禁止私域引流 | 评论区/正文/私信禁止"扣1"、"加我"、"vx"等 | 轻度限流15天，重度永久封号 |
| 发布行为拟人化 | 发布时间随机化，评论回复间隔符合人类规律 | 太规律会被判定为机器发布 |

## 成本估算

| 项目 | 成本 | 说明 |
|---|---|---|
| 硬件 | 0元 | 使用现有电脑，LLM用API不需要GPU |
| LLM API | 0-50元/月 | 免费API为主，额度不够时少量付费 |
| 住宅IP | 100-300元/月 | 主号用手机流量免费，副号需要住宅IP |
| 其他 | 0元 | 全部使用开源免费工具 |
| **合计** | **100-350元/月** | 低成本验证道路可行性 |

## 方案书

完整实施方案书见 `docs/AI社交媒体矩阵管理运营系统实施方案书_v1.5.md`

## 免责声明

- 本项目仅供学习研究使用，请勿用于违反平台规则的用途
- 社交媒体平台规则可能随时变化，使用前请确认最新规则
- AI生成内容必须主动标识，并经人工审核后发布
- 使用本项目产生的任何后果由使用者自行承担
