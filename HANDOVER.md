# DHSJR 导入安全改造交接记录

更新时间：2026-08-21（Asia/Shanghai）

## 当前 Git 状态

- 安全改造已合并到 `main`：[`toyjack/DHSJR#2`](https://github.com/toyjack/DHSJR/pull/2)
- merge commit：`48cd0692b08a98672ace87a1bb7d045b71db9c75`
- 跟踪 Issue：[toyjack/DHSJR#1](https://github.com/toyjack/DHSJR/issues/1)
- `main` 已包含预检、staging、全量差异报告和原子 production promotion 流程。
- production 已完成且结果验证通过；不要无必要地再次触发 production。

安全改造包含以下主要提交：

1. `6997780` — Ignore unmapped TSV fields during import
2. `095c1d1` — Remove duplicate RMK records
3. `c9a5568` — Validate TSV before database import
4. `c6c0b62` — Add safe staging import workflow
5. `4cae536` — Add atomic staging promotion workflow
6. `09d52f9` — Raise atomic promotion timeout
7. `c0f39b3` — Document successful production promotion

## 已完成工作

### 未映射字段

- 当前聚合 TSV 有 34 列，Supabase `dhsjr` 表有 23 列。
- 导入脚本现在只发送数据库已有的 23 个字段。
- 11 个新增字段仍保留在 TSV 中，但暂不写入数据库。
- 字段清单与后续迁移事项记录在 Issue #1。

### 重复主键

- 已从 `data/30-048-02_RMK.tsv` 和 `DHSJR_data_all.tsv` 删除四条完全相同的重复记录。
- 原重复 ID：
  - `30-048-02-030001`
  - `30-048-02-030002`
  - `30-048-02-030003`
  - `30-048-02-030004`
- 当前 TSV 共 387,268 行，重复 ID 为 0，格式异常为 0。

### 导入前预检

- 新增 `--preflight-only` 模式，完成后不会创建 Supabase 客户端。
- 在任何数据库连接和清表之前检查：
  - 必需表头
  - 行列结构
  - 必填值
  - `資料内漢字番号` 的整数类型
  - 空 ID
  - 重复 ID
- 重复 ID、必填值缺失、非整数及列数异常的负面测试均能正确失败。

### 安全 GitHub Actions 流程

- 默认模式改为 `preflight`。
- `staging` 固定写入 `dhsjr_staging`。
- `production` 需要额外输入 `IMPORT_PRODUCTION`。
- 导入后会比较数据库行数与 TSV 行数。
- 目标表不存在或不可访问时会在删除、插入之前安全中止。

### Staging 验证

- `supabase/create_dhsjr_staging.sql` 已由用户在 Supabase 手动执行。
- GitHub 仓库的 `SUPABASE_URL` 和 `SUPABASE_SERVICE_KEY` 已使用本地 `.env` 的当前值更新；本文件不记录任何 secret 值。
- 云端 preflight 成功：
  - https://github.com/toyjack/DHSJR/actions/runs/32447031118
- 第一次 staging 因旧 GitHub secrets 的 URL 无法解析而失败，但在清表前安全退出：
  - https://github.com/toyjack/DHSJR/actions/runs/32447074807
- 更新 secrets 后，完整 staging 导入成功，耗时 2 分 48 秒：
  - https://github.com/toyjack/DHSJR/actions/runs/32447272432

最终只读核对结果：

- `dhsjr_staging`：387,268 行
- 正式 `dhsjr`：387,265 行，未发生变化
- 两表 schema：均为 23 列，字段集合一致
- 六条代表记录（包含四个原重复 ID）的全部 23 个导入字段与 TSV 完全一致

### Staging 与 production 全量差异分析

- 新增只读工具 `scripts/compare_dhsjr_tables.py`，通过 PostgREST GET 分页读取并比较全部 23 个导入字段。
- 2026-08-21 全量比较结果：
  - staging：387,268 行
  - production：387,265 行
  - staging 新增：4 行
    - `30-048-02-030001`
    - `30-048-02-030002`
    - `30-048-02-030003`
    - `30-048-02-030004`
  - production 独有、发布时将删除：1 行
    - `30-048-02-012852`
  - 同 ID 内容变化：15,060 行
- 逐字段变化数量：
  - `単字_見出し`：5,252
  - `単字_出現形`：137
  - `漢語_見出し`：10,716
  - `漢語_出現形`：112
  - `漢語_alphabet`：2
  - `声点型`：82
  - `その他`：748
  - `出現位置`：3,537
  - `備考`：2
  - 其余 15 个字段：0
- 抽查确认变化是仓库数据相对当前 production 的真实修订，不是空值或空白字符归一化噪声。
- production 独有记录 `30-048-02-012852` 可追溯至提交 `d9a242b` 中的明确删除。

### 原子 promotion 实现与 Supabase 安装验证

- 新增 `supabase/promote_dhsjr_staging.sql`：
  - 校验确认文字与 staging 行数
  - 锁定 staging 和 production
  - 在同一事务中重建 `dhsjr_backup` 并复制当前 production
  - 清空 production 后从 staging 复制明确列出的 23 个字段
  - 在提交前再次核对写入行数
  - 任一步失败时由 PostgreSQL 整体回滚
- 新增 `scripts/promote_dhsjr.py`，只调用上述数据库函数，不再通过 REST 分批写 production。
- 新增 `supabase/restore_dhsjr_backup.sql`，供人工审查后的紧急恢复使用。
- 新增 `supabase/test_promote_dhsjr_staging.sql`，已在一次性本地 PostgreSQL 18 实例验证：
  - 正常 promotion 成功
  - 用触发器制造复制中途失败后，production 完整回滚
  - 失败后此前的 backup 也保持不变
- workflow 的 production 路径已改为：预检 → 全量差异报告 → 原子 promotion → 行数核对。
- 用户已于 2026-08-21 在 Supabase SQL Editor 安装数据库函数。
- 安装后通过两个安全失败分支验证 RPC 与护栏：
  - 错误确认文字返回 `Production confirmation is invalid`
  - 正确确认文字但期望行数为 1 时返回 `Staging row count 387268 does not match expected 1`
- 两次调用都在备份与清表前中止；验证后 staging 仍为 387,268 行，production 仍为 387,265 行。
- production promotion 尚未运行。
- 首次获批的 production workflow 在全量比较后调用原子函数，但约 8 秒时触发 PostgREST `statement_timeout`：
  - https://github.com/toyjack/DHSJR/actions/runs/32455104364
- 失败事务已完整回滚：staging 仍为 387,268 行、production 仍为 387,265 行，且未留下 `dhsjr_backup`。
- 根据 Supabase 的函数级超时机制，promotion 函数改为专用 60 秒上限；backup 改为不复制无需用于恢复的索引，以降低事务耗时。
- 用户重新安装修订后的函数后，production promotion 成功：
  - https://github.com/toyjack/DHSJR/actions/runs/32456930142
- 原子函数返回：
  - staging：387,268 行
  - production 发布前：387,265 行
  - backup：387,265 行
  - production 发布后：387,268 行
- workflow 发布后行数核对成功。
- 独立重新读取两表全部 23 个字段后，staging 与 production 的 ID 新增、删除、内容变化及每字段变化数量全部为 0。

### GitHub Actions 运行时升级与云端验证

- 根据 2026-08-21 GitHub 官方 latest release 信息升级为：
  - `actions/checkout@v7`
  - `actions/setup-python@v7`
  - `actions/upload-artifact@v7`
- workflow 增加最小 `contents: read` 权限，并在失败时上传差异报告（如存在）。
- 最新云端 preflight 已成功，未再出现 Node.js 运行时弃用警告：
  - https://github.com/toyjack/DHSJR/actions/runs/32449263932
- staging 使用 1,000 行批次时，清表后首批连续三次触发 statement timeout；production 未变化：
  - https://github.com/toyjack/DHSJR/actions/runs/32449329017
- 将批次降到 500 后 staging 完整成功（4 分 46 秒），行数核对为 387,268：
  - https://github.com/toyjack/DHSJR/actions/runs/32449489475
- 重新导入后再次完成全量只读比较，4 新增、1 删除、15,060 条内容变化及逐字段统计均未漂移。
- workflow 默认批次已相应调整为 500。

## 当前状态与尚未解决的问题

### 1. 发布前备份仍完整保留

2026-08-21 合并后再次只读核对：

- `dhsjr_backup`：387,265 行
- `dhsjr`：387,268 行
- `dhsjr_staging`：387,268 行

发布前数据仍保存在 `dhsjr_backup`。在确定保留期限前，不要执行恢复脚本、删除备份或再次运行 production。

### 2. 原子 production 已完成

函数护栏、失败回滚与成功路径均已完成云端验证。数据负责人已批准 15,060 条同 ID 内容变化、4 条新增和 1 条删除；发布后 production 与 staging 全量一致。

### 3. 新增字段仍未进入数据库

Issue #1 继续保持开启。需要决定字段类型、可空性、索引及迁移方案后，再更新导入 allowlist。

### 4. 安全改造已合并

PR #2 已于 2026-08-21 合并，`main` 已使用安全 workflow。远端功能分支暂时保留。

## 下次继续的建议顺序

1. 确定 `dhsjr_backup` 的保留期限；在明确决定前继续保留。
2. 为 11 个未映射字段决定是否持久化，以及列名、类型、可空性和索引。
3. 经审查后新增 schema migration、部署到 staging，并更新导入 allowlist。
4. 在 staging 全量验证通过并再次获得明确批准前，不要运行下一次 production。

## 安全约束

- 不要提交 `.env`。
- 不要在聊天、日志、PR 或 Issue 中输出 Supabase secret 值。
- 不要无必要地再次运行 production 模式。
- 不要直接清空正式 `dhsjr` 表。
- staging 可重新导入；正式表的后续变更需要再次获得明确批准。
