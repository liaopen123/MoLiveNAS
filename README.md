# MoLive NAS

在 NAS 上将 Apple Live Photo（HEIC/JPEG + MOV）增量转换为小米 / Google 兼容的 Motion Photo。

## 设计目标

- 飞牛原片目录只读，永不删除或改写母版。
- 视频方向正常时直接复制码流，只在旋转/编码不兼容时重编码。
- JPEG 方向正常时不重编码；HEIC 或带 EXIF 旋转的图片只编码一次。
- Apple HDR HEIC 在 Ultra HDR 链路完成前默认拒绝转换，不会静默产生偏亮/偏色的 SDR 成品。
- 仅用于明确测试时可设置 `MOLIVE_ALLOW_HDR_SDR_FALLBACK=true`；此时会清除原 HEIC 的 HDR、ICC 和 MakerNotes 声明。
- SQLite 记录增量状态，失败可重试，输出使用原子替换。
- 队列有积压时连续处理，只有队列清空后才等待下一个扫描周期。
- 同时写入 Google Motion Photo Container XMP 与小米 MicroVideo 兼容字段。

## 飞牛部署

1. 在飞牛文件管理中创建独立目录：

   ```text
   /vol1/1000/Photos          # 飞牛原片，挂载为只读
   /vol1/1000/MoLive/output   # Motion Photo 成品
   /vol1/1000/MoLive/data     # SQLite 和日志
   ```

2. 上传本项目，复制配置：

   ```bash
   cp .env.example .env
   ```

3. 根据实际路径修改 `.env` 和 `compose.yaml`。
   `PUID/PGID` 需与飞牛上拥有 MoLive 输出目录写权限的用户一致，可用 `id` 查看。

4. 启动：

   ```bash
   docker compose up -d --build
   ```

5. 打开 `http://NAS_IP:8787`查看状态。

### 只处理部署后新增的照片

如果 NAS 中已有照片已经手动转换，可在首次启动前设置：

```text
MOLIVE_BASELINE_ON_FIRST_RUN=true
```

首次扫描会把当时已有的 Live Photo 记录为 `baseline`，但不会转换。基线完成标记保存在
`/data/molive.sqlite3`，后续重启不会重复建立基线，新增或内容发生变化的照片会正常转换。
启用前应先等待本次手机备份完成，避免正在上传的新文件被计入旧照片基线。

> 状态页默认监听 `0.0.0.0:8787` 且未启用身份认证，页面会显示文件路径和失败信息。
> 只应在可信内网中访问，不要在路由器上做公网端口转发。
> 如需远程访问，请通过 VPN/Tailscale 或带鉴权的反向代理。

## 安全约束

- `/input` 必须使用 Docker `:ro` 只读挂载。
- `/output` 不要放在飞牛原始备份目录内。
- 服务只在文件大小连续两次稳定后才进入转换。

## 配对规则

1. 同目录、同文件名的 HEIC/JPEG + MOV。
2. Apple Content Identifier 一致。
3. 文件名 + 拍摄日期降级匹配（仅记录候选，默认不冒险转换）。

## 命令

```bash
python -m molive_nas scan      # 扫描并处理一次
python -m molive_nas daemon    # 持续监控
python -m molive_nas status    # 输出统计
python -m unittest discover -s tests
```

## 许可证

MIT。格式实现参考 Android Motion Photo Format 1.0 及 MIT 项目
`live_motion_photos_convert`，本工程未复用其 Apple MakerNotes 二进制样本。
