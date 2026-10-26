# 物流订单数据自动分析 Agent

上传一个物流订单 Excel，它会自动完成：**数据清洗 → 指标计算 → 异常识别 → 可视化图表 → AI 解读报告 → 自然语言问答**。

技术栈：Python · pandas · matplotlib · Streamlit · DeepSeek（大模型）· 博查（联网搜索）

---

## 一、功能一览

1. **自动清洗**：删除重复订单、统一日期格式、按承运商合理填充缺失运费等；
2. **指标看板**：总单量、签收率、准时率、异常率、平均配送时长、平均/总运费等；
3. **异常识别**：按规则自动标记超时、破损、丢失、拒收、疑似滞留，并可导出清单；
4. **可视化图表**：单量趋势、承运商时效/准时率/异常率、异常占比、区域与城市分布；
5. **AI 分析报告**：把精确计算的指标喂给大模型，**流式（打字机效果）** 生成可执行的诊断建议（不编造数字）；
6. **AI 问答（可联网）**：像和数据分析师对话一样，用自然语言提问，回答逐字流式显示；问到行业基准、政策、新闻等外部信息时，会自动调用**博查联网搜索**，并区分"本公司数据 / 外部信息"、附上参考链接；
7. **智能边界**：纯内部数据问题（如自家异常率、准时率）坚持只用本地计算结果，不乱搜、不编数字；没配搜索 Key 时也能正常问答，只是不联网。

> 说明：DeepSeek 默认开启"思考模式"（会先在后台推理数十秒再输出，且思考过程不显示）。本项目做的是"基于事实的解读"，不需要长时间推理，因此在 `llm_advisor.py` 里用 `extra_body={"thinking": {"type": "disabled"}}` 关闭了思考模式，首字延迟可从约 40 秒降到约 1 秒。若以后遇到需要复杂推理的问题，可改回 `"enabled"`。

---

## 二、项目结构

```
Logistics order data auto-analysis Agent/
├── venv/                    # Python 虚拟环境（项目专属工具箱）
├── data/raw/                # 放原始订单 Excel（含模拟数据）
├── output/
│   ├── charts/              # 生成的图表 PNG
│   └── reports/             # 异常订单清单等输出
├── src/
│   ├── generate_data.py     # 阶段1：生成 1000 单模拟订单
│   ├── data_loader.py       # 阶段2：读取与清洗
│   ├── analyzer.py          # 阶段3-4：指标计算 + 异常识别
│   ├── charts.py            # 阶段5：图表生成
│   ├── llm_advisor.py       # 大模型解读、问答、工具调用（function calling）
│   ├── search_client.py     # 联网搜索：调用博查 Web Search API
│   └── app.py               # 阶段7：Streamlit 网页（最终入口）
├── requirements.txt         # 依赖库清单
├── .env                     # 你的 API Key（DeepSeek / 博查，已被 gitignore，不提交）
└── .env.example             # 密钥模板
```

---

## 三、如何运行（在 VS Code 终端）

> 前提：终端前面有 `(venv)`，且当前在项目根目录。

### 1. （首次或需要时）生成模拟数据
```powershell
python src/generate_data.py
```
会在 `data/raw/logistics_orders.xlsx` 生成 1000 单数据。

### 2. 启动网页（最常用，只需要这条）
```powershell
streamlit run src/app.py
```
浏览器会自动打开 `http://localhost:8501`。
- 左侧点击「加载示例数据」或上传自己的 Excel；
- 停止网页：在终端按 `Ctrl + C`。

### 3. 各模块也可以单独运行（方便调试）
```powershell
python src/data_loader.py     # 只看清洗效果
python src/analyzer.py        # 只看指标 + 异常清单
python src/charts.py          # 只生成图表
python src/search_client.py   # 只测联网搜索
python src/llm_advisor.py     # 看 AI 报告 + 联网问答全过程
```

---

## 四、配置 API Key（换电脑时）

### 1）大模型 Key（必需）
1. 打开 https://platform.deepseek.com 注册登录、充值（10 元够用几百次）；
2. 左侧「API keys → 创建」，复制 `sk-` 开头的 Key；
3. 打开项目根目录 `.env`，把等号后替换成你的 Key（等号两边不加空格、不加引号）：
   ```
   DEEPSEEK_API_KEY=sk-你的真实key
   ```
4. 本项目使用模型 `deepseek-flash`（即 DeepSeek V4.1 Flash），接口地址 `https://api.deepseek.com`。

### 2）联网搜索 Key（可选，用于 AI 问答联网）
1. 微信扫码登录博查开放平台 https://open.bochaai.com（国内服务，无需翻墙）；
2. 左侧「API KEY 管理 → 创建 API Key」，复制 Key；
3. 左侧「资源包管理 → 免费试用 / Free Trial」订阅领取（否则没有调用次数，约 0.036 元/次）；
4. 填进 `.env`：
   ```
   BOCHA_API_KEY=sk-你的博查key
   ```
   不填也能用，只是 AI 问答不会联网，仅回答本公司数据问题。

> 安全：API Key 等同密码，绝不发给别人、不要贴到公开代码；`.env` 已加入 `.gitignore`。

---

## 五、换成真实数据（重要）

直接在网页左侧上传真实订单 Excel 即可。但要保证表头列名与程序一致，至少包含这些列（可按需在代码里改名）：

`订单号、承运商、发货城市、收货城市、收货区域、下单时间、发货时间、签收时间、配送时长(小时)、承诺时效(小时)、重量(kg)、运费(元)、订单状态、异常类型`

如果你的真实表列名不同，最简单的办法是在 Excel 里把列名改成和上面一致；
后续也可在 `src/data_loader.py` 里做一列「列名映射」来兼容。

---

## 六、可继续扩展的方向

- 增加更多指标：客诉率、破损率趋势、承运商×区域交叉分析；
- 支持多文件批量分析、自动扫描文件夹定时出报告；
- 导出 Word/PDF 版自动报告；
- 接入更多数据源（数据库、物流系统 API）；
- 增加图表类型（运费重量散点、箱线图）；
- 让 AI 自动生成"给领导的 200 字周报"。
