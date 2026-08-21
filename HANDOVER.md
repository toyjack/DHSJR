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

### 原子 promotion 实现（尚未安装到 Supabase）

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
- 这些改动当前只在本地工作区，数据库函数尚未在 Supabase 执行，production 也没有运行。

### GitHub Actions 运行时升级（尚未云端验证）

- 根据 2026-08-21 GitHub 官方 latest release 信息升级为：
  - `actions/checkout@v7`
  - `actions/setup-python@v7`
  - `actions/upload-artifact@v7`
- workflow 增加最小 `contents: read` 权限，并在失败时上传差异报告（如存在）。

## 尚未解决的问题

### 1. 原子 promotion 尚未安装和云端验证

需要先审查 `supabase/promote_dhsjr_staging.sql`，再由用户在 Supabase SQL Editor 安装函数。安装后先重新运行云端 preflight 与 staging；不要直接运行 production。

### 2. 全量内容变化需要发布审查

已确定有 15,060 条同 ID 内容变化、4 条新增和 1 条删除。虽然抽查与 Git 历史支持这些是实际数据修订，但在 production promotion 前仍应由数据负责人确认本次差异范围可接受。

### 3. 新增字段仍未进入数据库

Issue #1 继续保持开启。需要决定字段类型、可空性、索引及迁移方案后，再更新导入 allowlist。

### 4. GitHub Actions 升级尚未云端验证

版本已升级到 v7，但还没有提交或运行 GitHub Actions。需要通过新的 preflight 与 staging run 确认 GitHub-hosted runner、LFS 与 artifact 行为正常。

### 5. Draft PR 尚未合并

功能分支和远端同步，但 `main` 仍使用旧 workflow。完成差异分析和原子发布设计前，不要将 PR 标记为 ready 或运行 production。

## 下次继续的建议顺序

1. 审查并提交当前本地改动，推送到 `fix/ignore-new-tsv-fields`。
2. 由用户在 Supabase SQL Editor 执行 `supabase/promote_dhsjr_staging.sql`；不要执行恢复 SQL。
3. 重新运行云端 preflight。
4. 重新运行完整 staging，并复跑全量差异报告。
5. 更新 Draft PR，附上差异统计、本地回滚测试和新的 Actions run 链接。
6. 由数据负责人确认 4 新增、1 删除、15,060 条内容变化可发布。
7. 审查完成后再决定是否将 PR 标记 ready、合并及运行 production。

## 安全约束

- 不要提交 `.env`。
- 不要在聊天、日志、PR 或 Issue 中输出 Supabase secret 值。
- 不要运行当前 production 模式。
- 不要直接清空正式 `dhsjr` 表。
- staging 可重新导入；正式表在明确批准前保持只读。
