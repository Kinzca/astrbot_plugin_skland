"""
AstrBot Plugin - 森空岛签到 (Skland Sign-In)

Commands:
- skd (group): Show sign-in status for all bound users in the group
- skd (private): Show user's own sign-in status
- skdlogin (private): Login with token and immediately sign in
- skdlogout (private): Logout and remove token
- skdusers (all): Show users and stats 

Config (AstrBot plugin config):
- auto_sign_enabled: 自动签到开关
- auto_sign_hour: 自动签到时间（小时，0-23）
- show_player_name: 显示玩家昵称（否则显示QQ昵称）
- auto_sign_delay: 签到延时
- max_users: 最大用户数量
- allowed_group_ids: 允许响应群聊命令的群号，多个群号用逗号分隔，留空表示不限制
- auto_sign_group_report_enabled: 自动签到后是否群内汇报
- auto_sign_report_group_ids: 自动签到结果汇报群号，多个群号用逗号分隔
- auto_sign_report_platform_id: 自动签到结果汇报使用的平台 ID
- auto_sign_group_report_show_details: 自动签到群内汇报是否显示个人明细
- auto_sign_group_report_tip: 自动签到群内汇报末尾提示
"""

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from astrbot.core.star.filter.permission import PermissionType
import astrbot.api.message_components as Comp
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.config import put_config
import asyncio, random

from .skland_api import SklandAPI

PLUGIN_NAME = "astrbot_plugin_skland"


@register(PLUGIN_NAME, "AstrBot", "森空岛自动签到插件", "1.3.0")
class SklandPlugin(Star):
    """森空岛签到插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.api = SklandAPI(max_retries=3)
        self.scheduler = AsyncIOScheduler()
        self._init_config()

    def _init_config(self):
        """注册后台配置项"""
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到开关",
            key="auto_sign_enabled",
            value=True,
            description="开启后，将在指定时间自动为所有已注册用户签到，并私发结果"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到时间（小时）",
            key="auto_sign_hour",
            value=1,
            description="自动签到执行的小时（0-23），默认凌晨1点"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="显示玩家名称",
            key="show_player_name",
            value=True,
            description="开启后，将在签到结果中显示森空岛昵称，否则显示QQ昵称"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到的延迟",
            key="auto_sign_delay",
            value=10,
            description="开启后，将在签到时进行向后随机延迟（随机范围 0 至 设定的秒数）"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="最大用户数",
            key="max_users",
            value=10,
            description="允许绑定的最大用户数量，0表示无限制"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="允许响应的群号",
            key="allowed_group_ids",
            value="759775061",
            description="多个群号用英文逗号分隔；留空表示不限制群聊命令"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到后群内汇报",
            key="auto_sign_group_report_enabled",
            value=True,
            description="开启后，自动签到完成会在指定群聊发送汇总，详细结果仍私聊本人"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到汇报群号",
            key="auto_sign_report_group_ids",
            value="759775061",
            description="多个群号用英文逗号分隔；留空时使用允许响应的群号"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到汇报平台ID",
            key="auto_sign_report_platform_id",
            value="qq-test",
            description="AstrBot 平台配置 ID；当前 OneBot 平台为 qq-test"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到群汇报显示明细",
            key="auto_sign_group_report_show_details",
            value=False,
            description="关闭时群内只显示人数汇总，个人详细结果只私聊本人"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到群汇报提示",
            key="auto_sign_group_report_tip",
            value="输入 /skdhelp 获取帮助",
            description="自动签到群内汇报末尾附带的提示语"
        )

    def _get_config(self) -> dict:
        """获取当前配置"""
        return {
            "auto_sign_enabled": self.config.get("auto_sign_enabled", True),
            "auto_sign_hour": self.config.get("auto_sign_hour", 1),
            "show_player_name": self.config.get("show_player_name", True),
            "auto_sign_delay": self.config.get("auto_sign_delay", 10),
            "max_users": self.config.get("max_users", 10),
            "allowed_group_ids": self.config.get("allowed_group_ids", "759775061"),
            "auto_sign_group_report_enabled": self.config.get("auto_sign_group_report_enabled", True),
            "auto_sign_report_group_ids": self.config.get("auto_sign_report_group_ids", "759775061"),
            "auto_sign_report_platform_id": self.config.get("auto_sign_report_platform_id", "qq-test"),
            "auto_sign_group_report_show_details": self.config.get("auto_sign_group_report_show_details", False),
            "auto_sign_group_report_tip": self.config.get(
                "auto_sign_group_report_tip",
                "输入 /skdhelp 获取帮助",
            ),
        }

    def _normalize_group_ids(self, value) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            parts = value.replace("，", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = [value]
        return {str(part).strip() for part in parts if str(part).strip()}

    def _group_command_allowed(self, group_id) -> bool:
        allowed_group_ids = self._normalize_group_ids(
            self._get_config().get("allowed_group_ids", "759775061")
        )
        if not group_id or not allowed_group_ids:
            return True
        return str(group_id).strip() in allowed_group_ids

    def _log_blocked_group(self, command_name: str, group_id):
        logger.info(f"森空岛命令 {command_name} 已在未授权群 {group_id} 中忽略")

    def _get_help_text(self) -> str:
        return (
            "———获取 Token————\n"
            "1、登录 https://www.skland.com/\n"
            "2、访问 https://web-api.skland.com/account/info/hg\n"
            "3、找到返回的 JSON 中的 {\"content\":\"XXX\"}\n"
            "4、复制 XXX 部分\n"
            "———登录与签到———\n"
            "1、私聊发送 /skdlogin XXX 进行登录\n"
            "2、登录成功后会自动执行一次签到\n"
            "3、之后可以发送 /skd 查看签到状态\n"
            "————————————"
        )

    def _get_display_name(self, user_id: str, user_data: dict, nickname: str = "") -> str:
        name = nickname or user_data.get("nickname") or user_data.get("last_username") or user_id
        return str(name).strip() or str(user_id)

    async def initialize(self):
        """插件初始化"""
        logger.info("森空岛签到插件已加载")
        config = self._get_config()
        if config.get("auto_sign_enabled", False):
            hour = config.get("auto_sign_hour", 1)
            self._start_auto_sign_job(hour)
        if not self.scheduler.running:
            self.scheduler.start()

    async def terminate(self):
        """插件卸载"""
        if self.scheduler.running:
            self.scheduler.shutdown()
        await self.api.close()
        logger.info("森空岛签到插件已卸载")

    # ==================== Auto Sign-In ====================

    def _start_auto_sign_job(self, hour: int = 1):
        """启动自动签到定时任务"""
        hour = max(0, min(23, hour))
        trigger = CronTrigger(hour=hour, minute=0)
        try:
            self.scheduler.remove_job("skland_auto_sign")
        except Exception:
            pass

        self.scheduler.add_job(
            self._auto_sign_all_users,
            trigger=trigger,
            id="skland_auto_sign",
            misfire_grace_time=3600,
        )
        logger.info(f"森空岛自动签到任务已启动，每天 {hour:02d}:00 执行")

    async def _auto_sign_all_users(self):
        """为所有已注册用户执行自动签到"""
        config = self._get_config()
        if not config.get("auto_sign_enabled", False):
            logger.info("自动签到已关闭，跳过执行")
            return

        logger.info("开始执行自动签到...")
        users = await self.get_kv_data("users", {})
        if not users:
            logger.info("没有已注册的用户，跳过自动签到")
            return
        
        # 自动签到的最大随机延时时间
        max_delay = config.get("auto_sign_delay", 10)
        group_report_rows = []
        success_users = 0
        failed_users = 0

        for user_id, user_data in users.items():
            # 随机延时的核心代码
            if max_delay > 0:
                delay = random.uniform(0, max_delay)
                logger.info(f"处理下一个用户前等待 {delay:.2f} 秒")
                await asyncio.sleep(delay)
            
            if "token" not in user_data:
                continue

            display_name = self._get_display_name(user_id, user_data)
            try:
                token = user_data["token"]
                results, nickname = await self.api.do_full_sign_in(token)
                display_name = self._get_display_name(user_id, user_data, nickname)

                # 更新签到状态
                for r in results:
                    if r.game == "明日方舟" and self._is_signed_today(r):
                        user_data.setdefault("last_sign", {})["arknights"] = datetime.now().strftime("%Y-%m-%d")
                    elif r.game == "终末地" and self._is_signed_today(r):
                        user_data.setdefault("last_sign", {})["endfield"] = datetime.now().strftime("%Y-%m-%d")

                # 构建消息
                message = f"🎮 森空岛自动签到结果\n\n{self._format_sign_status(results, nickname)}"
                await self._send_private_message(user_id, user_data, message)
                users[user_id] = user_data
                if self._has_failed_group_report_result(results):
                    failed_users += 1
                elif self._has_group_reportable_result(results):
                    success_users += 1

                group_report_row = self._format_group_report_row(display_name, results)
                if group_report_row:
                    group_report_rows.append(group_report_row)
                logger.info(f"用户 {user_id} ({nickname}) 自动签到完成")
            except Exception as e:
                logger.error(f"用户 {user_id} 自动签到失败: {e}")
                message = f"⚠️ 自动签到失败\n错误: {str(e)}\n请使用 /skdlogin 重新登录"
                await self._send_private_message(user_id, user_data, message)
                failed_users += 1
                group_report_rows.append(f"⚠️ {display_name}: 签到失败，详情已私聊本人")

        await self.put_kv_data("users", users)
        await self._send_group_report(config, group_report_rows, success_users, failed_users)
        logger.info("自动签到执行完毕")

    async def _send_private_message(self, user_id: str, user_data: dict, message: str):
        """使用统一会话ID发送私聊消息"""
        try:
            umo = user_data.get("umo")
            if not umo:
                logger.warning(f"用户 {user_id} 没有统一会话ID，无法发送私聊消息")
                return

            message_chain = MessageChain().message(message)
            await self.context.send_message(umo, message_chain)
            logger.info(f"已发送私聊消息给用户 {user_id}")
        except Exception as e:
            logger.error(f"发送私聊消息失败: {e}")

    async def _send_group_report(self, config: dict, rows: list[str], success_users: int, failed_users: int):
        """向配置的群聊发送自动签到汇总。"""
        if not config.get("auto_sign_group_report_enabled", True):
            return
        if not rows:
            logger.info("自动签到没有可汇报的用户，跳过群内汇报")
            return

        group_ids = self._normalize_group_ids(config.get("auto_sign_report_group_ids"))
        if not group_ids:
            group_ids = self._normalize_group_ids(config.get("allowed_group_ids", "759775061"))
        if not group_ids:
            logger.warning("未配置自动签到汇报群号，跳过群内汇报")
            return

        platform_id = str(config.get("auto_sign_report_platform_id") or "qq-test").strip()
        if not platform_id:
            logger.warning("未配置自动签到汇报平台 ID，跳过群内汇报")
            return

        total_users = success_users + failed_users
        today = datetime.now().strftime("%Y-%m-%d")
        tip = str(config.get("auto_sign_group_report_tip") or "").strip()
        lines = [
            f"森空岛自动签到完成（{today}）",
            f"今日处理 {total_users} 人：成功 {success_users} 人，失败 {failed_users} 人",
            "详细结果已私聊发送给各位绑定用户。",
        ]
        if config.get("auto_sign_group_report_show_details", False):
            lines.extend(["", *rows])
        if tip:
            lines.extend(["", tip])

        message_chain = MessageChain().message("\n".join(lines))
        for group_id in sorted(group_ids):
            session = f"{platform_id}:GroupMessage:{group_id}"
            try:
                sent = await self.context.send_message(session, message_chain)
                if sent:
                    logger.info(f"已向群 {group_id} 发送森空岛自动签到汇总")
                else:
                    logger.warning(f"森空岛自动签到汇总发送失败：未找到平台 {platform_id}")
            except Exception as e:
                logger.error(f"发送森空岛自动签到群汇报失败，群 {group_id}: {e}")

    # ==================== Helpers ====================

    def _is_signed_today(self, result) -> bool:
        if result.success:
            return True
        error = result.error.lower() if result.error else ""
        return any(k in error for k in ["已签到", "请勿重复", "重复签到", "already", "签到过", "今日已"])

    def _format_sign_status(self, results: list, nickname: str = "") -> str:
        if not results:
            return "没有绑定游戏"
        lines = []
        if nickname:
            lines.append(f"【{nickname}】")
        for r in results:
            if r.success or self._is_signed_today(r):
                award = ", ".join(r.awards) if getattr(r, "awards", None) else "无奖励"
                lines.append(f"{r.game} 已签到 ({award})")
            else:
                lines.append(f"{r.game} 签到失败: {r.error}")
        return "\n".join(lines)

    def _has_failed_result(self, results: list) -> bool:
        if not results:
            return True
        return any(not (r.success or self._is_signed_today(r)) for r in results)

    def _is_missing_game_data_result(self, result) -> bool:
        if result.success or self._is_signed_today(result):
            return False

        error = str(getattr(result, "error", "") or "").strip().lower()
        return any(
            keyword in error
            for keyword in [
                "没有角色数据",
                "无角色数据",
                "暂无角色数据",
                "no role",
                "no character",
            ]
        )

    def _group_report_results(self, results: list) -> list:
        return [r for r in results if not self._is_missing_game_data_result(r)]

    def _has_group_reportable_result(self, results: list) -> bool:
        return bool(self._group_report_results(results))

    def _has_failed_group_report_result(self, results: list) -> bool:
        reportable_results = self._group_report_results(results)
        if not reportable_results:
            return False
        return any(not (r.success or self._is_signed_today(r)) for r in reportable_results)

    def _format_group_report_row(self, nickname: str, results: list) -> str:
        reportable_results = self._group_report_results(results)
        if not reportable_results:
            return ""

        parts = []
        has_failed = False
        for r in reportable_results:
            ok = r.success or self._is_signed_today(r)
            has_failed = has_failed or not ok
            game_name = "方舟" if r.game == "明日方舟" else "终末" if r.game == "终末地" else r.game
            parts.append(f"{game_name}{'✅' if ok else '⚠️'}")

        prefix = "⚠️" if has_failed else "✅"
        return f"{prefix} {nickname}: {' / '.join(parts)}"

    # ==================== Commands ====================

    @filter.command("skdhelp")
    async def skdhelp(self, event: AstrMessageEvent):
        """森空岛签到插件帮助"""
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id and not self._group_command_allowed(group_id):
            self._log_blocked_group("skdhelp", group_id)
            return

        yield event.plain_result(self._get_help_text())

    @filter.command("sdkhelp")
    async def sdkhelp(self, event: AstrMessageEvent):
        """兼容 skdhelp 的常见误拼写"""
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id and not self._group_command_allowed(group_id):
            self._log_blocked_group("sdkhelp", group_id)
            return

        yield event.plain_result(self._get_help_text())

    @filter.command("sdk")
    async def sdk(self, event: AstrMessageEvent, subcommand: str = ""):
        """兼容 /sdk help 的常见误拼写"""
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id and not self._group_command_allowed(group_id):
            self._log_blocked_group("sdk", group_id)
            return

        if subcommand.strip().lower() in ("", "help", "帮助"):
            yield event.plain_result(self._get_help_text())
        else:
            yield event.plain_result("你可能想输入 /skdhelp 查看森空岛签到使用指南。")
    
    # @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.command("skdlogin")
    async def skdlogin(self, event: AstrMessageEvent, token: str = ""):
        # 验证是否在群内登录 如果是 则提示用户撤回消息且在私聊中使用
        group_id = getattr(event.message_obj, "group_id", None)
        user_name = event.get_sender_name()
        if group_id:
            yield event.plain_result(" 请在私聊中使用此命令登录\n为保护隐私，请将发送在群内的登录消息撤回")
            return
        
        config = self._get_config()
        
        user_id = event.get_sender_id()
        users = await self.get_kv_data("users", {})
        max_users = config.get("max_users", 10)
        
        if user_id not in users and max_users > 0 and len(users) >= max_users:
            yield event.plain_result(f"❌ 绑定失败：已达到最大用户数限制（{max_users}个）\n请联系管理员调整配置")
            return
        
        token = token.strip()
        if not token:
            yield event.plain_result(
                "你还没有带上 content。\n\n"
                f"{self._get_help_text()}"
            )
            return
        yield event.plain_result("正在登录并签到，请稍候...")
        try:
            results, nickname = await self.api.do_full_sign_in(token)
            user_data = {
                "token": token,
                "nickname": nickname,
                "last_username": user_name,
                "last_sign": {},
                "bound_at": datetime.now().isoformat(),
                "platform_name": event.get_platform_name(),
                "umo": event.unified_msg_origin,  # 保存统一会话ID
            }
            for r in results:
                if r.game == "明日方舟" and self._is_signed_today(r):
                    user_data["last_sign"]["arknights"] = datetime.now().strftime("%Y-%m-%d")
                elif r.game == "终末地" and self._is_signed_today(r):
                    user_data["last_sign"]["endfield"] = datetime.now().strftime("%Y-%m-%d")
            await self.put_kv_data("users", {**(await self.get_kv_data("users", {})), user_id: user_data})
            yield event.plain_result(f"登录成功！\n{self._format_sign_status(results, nickname)}")
        except Exception as e:
            logger.error(f"skdlogin失败: {e}")
            yield event.plain_result(f"登录失败: {str(e)}")

    # @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.command("skdlogout")
    async def skdlogout(self, event: AstrMessageEvent):
        # 验证是否在群内登出 如果是 则提示用户撤回消息且在私聊中使用
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id:
            yield event.plain_result(" 请在私聊中使用此命令登出\n为保护隐私，请将发送在群内的登出消息撤回")
            return
        
        user_id = event.get_sender_id()
        users = await self.get_kv_data("users", {})
        if user_id in users:
            del users[user_id]
            await self.put_kv_data("users", users)
            yield event.plain_result("已退出登录并清除绑定信息")
        else:
            yield event.plain_result("您尚未绑定森空岛账号")

    @filter.command("skdusers")
    async def skdusers(self, event: AstrMessageEvent):
        """查询当前注册用户数量"""
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id and not self._group_command_allowed(group_id):
            self._log_blocked_group("skdusers", group_id)
            return
        
        users = await self.get_kv_data("users", {})
        groups = await self.get_kv_data("groups", {})
        config = self._get_config()
        max_users = config.get("max_users", 10)
        
        # 计算群聊分布
        group_stats = []
        for group_id, user_ids in groups.items():
            if user_ids:
                group_name = group_id  # 这里可以尝试获取群名称，如果可能的话
                group_stats.append(f"  • 群 {group_name}: {len(user_ids)} 人")
        
        # 计算在线用户（最近7天有登录的用户）
        online_users = 0
        for user_data in users.values():
            if user_data.get("last_sign"):
                online_users += 1
        
        # 构建统计信息
        lines = [
            "📊 森空岛签到用户统计",
            "═══════════════════",
            f"📝 总注册用户: {len(users)} 人",
            # f"📈 今日活跃: {online_users} 人",
            f"📉 未签到用户: {len(users) - online_users} 人",
        ]
        
        # 检查管理员
        if event.is_admin():
            if max_users > 0:
                remaining = max(0, max_users - len(users))
                lines.append(f"🎯 最大限制: {max_users} 人")
                lines.append(f"🆓 剩余名额: {remaining} 人")
            
            # 限定私信查看
            if not getattr(event.message_obj, "group_id", None):
                # 添加群聊分布
                if group_stats:
                    lines.append("\n📌 群聊分布（仅代表群内同玩的数量）:")
                    lines.extend(group_stats)
                # 添加用户列表（如果用户数不多）
                if len(users) <= 20:
                    lines.append("\n👤 用户列表:")
                    for user_id, user_data in users.items():
                        nickname = user_data.get("nickname") or user_data.get("last_username", "未知")
                        last_sign = list(user_data.get("last_sign", {}).values())[-1] if user_data.get("last_sign") else "未签到"
                        lines.append(f"  • {nickname} (最后签到: {last_sign})")
                else:
                    lines.append(f"\n💡 用户数过多，不显示详细列表")
            else:
                lines.append(f"\n💡 如需查看详细用户列表请私信")
        yield event.plain_result("\n".join(lines))

    @filter.command("skd")
    async def skd(self, event: AstrMessageEvent, subcommand: str = ""):
        """群聊显示群成员签到状态，私聊显示自己"""
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        group_id = getattr(event.message_obj, "group_id", None)
        is_group = bool(group_id)
        if is_group and not self._group_command_allowed(group_id):
            self._log_blocked_group("skd", group_id)
            return
        if subcommand.strip().lower() in ("help", "帮助"):
            yield event.plain_result(self._get_help_text())
            return

        users_data = await self.get_kv_data("users", {})

        if is_group: # 群聊模式
            # 如果发送者已绑定，自动添加到该群
            if user_id in users_data:
                groups = await self.get_kv_data("groups", {})
                if group_id not in groups:
                    groups[group_id] = []
                if user_id not in groups[group_id]:
                    groups[group_id].append(user_id)
                    await self.put_kv_data("groups", groups)
            
            message_lines = [" 森空岛签到统计", "═══════════════", "方舟 | 终末 | 昵称", "-----------------"]
            group_users = (await self.get_kv_data("groups", {})).get(group_id, [])
            for uid in group_users:
                user_data = users_data.get(uid)
                if not user_data:
                    continue
                try:
                    results, nickname = await self.api.do_full_sign_in(user_data["token"])
                    
                    # 滚动更新昵称，每次将发送者昵称更新到用户数据中，确保昵称是最新的
                    if user_id in str(users_data.get("umo")):
                        # 当用户名不一致则更新
                        if user_name != user_data.get("last_username"):
                            await self.put_kv_data("users", {**(await self.get_kv_data("users", {})), user_id: {"last_username": nickname}})
                    
                    # 如果配置不显示玩家名称，或者昵称获取为空，则使用QQ昵称显示
                    if nickname == None or nickname.strip() == "" or not self.config.get("show_player_name", True):
                        nickname = user_data.get("last_username").strip() or "(未知)"
                    
                    user_data["nickname"] = nickname
                    for r in results:
                        if r.game == "明日方舟" and self._is_signed_today(r):
                            user_data.setdefault("last_sign", {})["arknights"] = datetime.now().strftime("%Y-%m-%d")
                        elif r.game == "终末地" and self._is_signed_today(r):
                            user_data.setdefault("last_sign", {})["endfield"] = datetime.now().strftime("%Y-%m-%d")
                    
                    users_data[uid] = user_data
                    
                    ak_icon = "✅" if user_data.get("last_sign", {}).get("arknights") else "❌"
                    ef_icon = "✅" if user_data.get("last_sign", {}).get("endfield") else "❌"
                    message_lines.append(f" {ak_icon} | {ef_icon} | {nickname}")
                except:
                    message_lines.append(" ⚠️ | ⚠️ | (Error)")
            await self.put_kv_data("users", users_data)
            yield event.plain_result("\n".join(message_lines))
        else: # 私聊模式
            user_data = users_data.get(user_id)
            if not user_data:
                yield event.plain_result("你还未绑定账号，请使用 /skdlogin <token>")
                return
            try:
                results, nickname = await self.api.do_full_sign_in(user_data["token"])
                response = self._format_sign_status(results, nickname)
                yield event.plain_result(response)
            except Exception as e:
                yield event.plain_result(f"查询失败: {str(e)}")
