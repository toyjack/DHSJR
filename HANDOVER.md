# DHSJR 导入安全改造交接记录

更新时间：2026-08-21（Asia/Shanghai）

## 当前 Git 状态

- 工作分支：`fix/ignore-new-tsv-fields`
- Draft PR：[toyjack/DHSJR#2](https://github.com/toyjack/DHSJR/pull/2)
- 跟踪 Issue：[toyjack/DHSJR#1](https://github.com/toyjack/DHSJR/issues/1)
- PR 尚未合并，`main` 仍是旧的高风险导入流程。
- 不要从 `main` 触发 production 导入。

本分支包含以下提交：

1. `6997780` — Ignore unmapped TSV fields during import
2. `095c1d1` — Remove duplicate RMK records
3. `c9a5568` — Validate TSV before database import
4. `c6c0b62` — Add safe staging import workflow

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

## 尚未解决的问题

### 1. 正式发布不是原子操作

当前 production 模式仍会先清空正式表，再通过 REST 分 388 批写入。中途失败可能留下空表或部分数据，因此尚不能安全运行 production。

推荐改为数据库内的单事务发布：

1. 对 staging 做完整验证。
2. 创建正式表备份或可恢复快照。
3. 在 PostgreSQL 单一事务内锁定 `dhsjr`。
4. 清空并从 `dhsjr_staging` 复制 23 个字段。
5. 在事务内验证行数；失败则整体回滚。

### 2. 尚未完成 staging 与 production 的全量差异分析

下一步优先执行只读比较：

- staging 新增 ID
- production 独有、将被删除的 ID
- 同一 ID 下内容发生变化的记录
- 每个字段的变化数量

不要仅根据 `387,268 - 387,265 = 3` 推断只有三条新增记录。

### 3. 新增字段仍未进入数据库

Issue #1 继续保持开启。需要决定字段类型、可空性、索引及迁移方案后，再更新导入 allowlist。

### 4. GitHub Actions 版本警告

运行时出现 Node.js 20 弃用警告，涉及 `actions/checkout@v4`、`actions/setup-python@v5`，失败日志路径还涉及 `actions/upload-artifact@v4`。升级前应核对各 Action 当前稳定版本。

### 5. Draft PR 尚未合并

功能分支和远端同步，但 `main` 仍使用旧 workflow。完成差异分析和原子发布设计前，不要将 PR 标记为 ready 或运行 production。

## 下次继续的建议顺序

1. 切换到 `fix/ignore-new-tsv-fields` 并确认工作区干净。
2. 只读比较 `dhsjr_staging` 与 `dhsjr` 的全部 23 个字段。
3. 设计原子 promotion SQL 和备份/恢复步骤。
4. 在测试表上验证成功路径和故意失败后的回滚。
5. 修改 workflow，使 production 只调用已验证的原子 promotion。
6. 升级 GitHub Actions 版本并重新运行 preflight、staging。
7. 更新 Draft PR 与 Issue #1；审查完成后再决定是否合并。

## 安全约束

- 不要提交 `.env`。
- 不要在聊天、日志、PR 或 Issue 中输出 Supabase secret 值。
- 不要运行当前 production 模式。
- 不要直接清空正式 `dhsjr` 表。
- staging 可重新导入；正式表在明确批准前保持只读。
