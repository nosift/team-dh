# Team-DH

这是一个面向 Zeabur/容器部署的 **ChatGPT Team 席位兑换码系统**：管理员在后台维护 Team、生成/禁用/删除兑换码、查看兑换记录与 Team 统计；用户通过“邮箱 + 兑换码”兑换席位邀请。

## 功能
- 兑换码：生成（默认每次 4 个）、启用/禁用、删除、用尽标记（`used_up`）
- 兑换逻辑：邮箱校验、防重复兑换、席位检查、并发锁（避免超发）、IP 限流
- 管理后台：Team 管理、兑换记录、Team 统计、批量删除（兑换码/记录）
- 持久化：推荐挂载 `/data`，镜像更新不丢数据
- 真实 IP：支持 `Forwarded` / `X-Forwarded-For` / `X-Real-IP`（`TRUST_PROXY=true`）

## 部署（Zeabur 推荐）
1) **Volumes**：挂载一个持久化卷到 `/data`
2) **Variables**（示例）
```
ADMIN_PASSWORD=your-password
SECRET_KEY=<random-64-hex>
DATA_DIR=/data
REDEMPTION_DATABASE_FILE=/data/redemption.db
TRUST_PROXY=true
REDEMPTION_CODE_LOCK_SECONDS=120
```
3) **镜像**：`ghcr.io/nosift/team-dh:latest`

## 访问
- 兑换页面：`/`
- 管理后台：`/admin`

## 关于“批量注册/CRS”
本仓库早期来自上游项目，代码中仍保留了一些“批量注册/CRS”等脚本文件，但 **镜像默认入口只启动兑换码系统**（`web_server:app`）。如果你希望彻底移除这些旧脚本与相关依赖说明，我可以继续帮你清理。

## License
MIT License - 详见 [LICENSE](LICENSE)。

