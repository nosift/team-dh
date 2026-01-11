'''
成员租约模型和状态机定义
'''

from enum import Enum
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


class LeaseStatus(str, Enum):
    '''租约状态枚举'''
    PENDING = 'pending'              # 已发送邀请,等待用户接受
    ACTIVE = 'active'                # 已加入,租期进行中
    EXPIRING = 'expiring'            # 即将到期(可选,用于提前提醒)
    TRANSFERRING = 'transferring'    # 正在执行转移操作
    FAILED = 'failed'                # 转移失败,需人工介入
    CANCELLED = 'cancelled'          # 已取消(用户退出等)

    @classmethod
    def is_valid_transition(cls, from_status: str, to_status: str) -> bool:
        '''检查状态转换是否合法'''
        valid_transitions = {
            cls.PENDING: {cls.ACTIVE, cls.FAILED, cls.CANCELLED},
            cls.ACTIVE: {cls.EXPIRING, cls.TRANSFERRING, cls.CANCELLED},
            cls.EXPIRING: {cls.TRANSFERRING, cls.CANCELLED},
            cls.TRANSFERRING: {cls.PENDING, cls.ACTIVE, cls.FAILED},
            cls.FAILED: {cls.TRANSFERRING, cls.CANCELLED},
            cls.CANCELLED: set(),  # 终态
        }
        return to_status in valid_transitions.get(from_status, set())


class SyncReason(str, Enum):
    '''同步失败原因枚举'''
    MEMBER_NO_TIME = 'member_no_time'          # 成员列表无加入时间字段
    INVITE_NOT_ACCEPTED = 'invite_not_accepted'  # 邀请未被接受
    INVITE_ERROR = 'invite_error'              # 拉取 invites 失败
    MEMBER_ERROR = 'member_error'              # 拉取 members 失败
    NOT_JOINED = 'not_joined'                  # 未找到已加入证据


@dataclass
class MemberLease:
    '''成员租约数据模型'''
    email: str
    team_name: str
    team_account_id: Optional[str]

    # 时间字段 - 明确分离
    created_at: datetime      # 租约创建时间(兑换时间)
    invited_at: datetime      # 发送邀请时间
    joined_at: Optional[datetime]  # 用户接受邀请时间
    expires_at: datetime      # 到期时间(基于 joined_at)

    # 状态和计数
    status: LeaseStatus
    transfer_count: int = 0
    attempts: int = 0

    # 重试控制
    next_attempt_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    @property
    def is_pending(self) -> bool:
        '''是否等待用户接受邀请'''
        return self.status == LeaseStatus.PENDING and self.joined_at is None

    @property
    def is_active(self) -> bool:
        '''是否处于活跃租期'''
        return self.status == LeaseStatus.ACTIVE and self.joined_at is not None

    @property
    def is_expired(self) -> bool:
        '''是否已到期'''
        return self.expires_at <= datetime.now()

    @property
    def actual_term_days(self) -> Optional[int]:
        '''实际使用天数(如果已加入)'''
        if not self.joined_at:
            return None
        end = min(datetime.now(), self.expires_at)
        return (end - self.joined_at).days


@dataclass
class LeaseEvent:
    '''租约事件模型'''
    email: str
    action: str
    from_team: Optional[str] = None
    to_team: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None


class LeaseAction(str, Enum):
    '''租约事件动作枚举'''
    CREATED = 'created'                    # 租约创建
    INVITED = 'invited'                    # 发送邀请
    JOINED = 'joined'                      # 用户加入
    JOINED_FALLBACK = 'joined_fallback'    # 近似加入时间
    SYNC_SKIP = 'sync_skip'                # 跳过同步
    SYNC_INVITE_STATUS = 'sync_invite_status'  # 同步邀请状态
    SYNC_INVITE_ERROR = 'sync_invite_error'    # 同步邀请失败
    SYNC_MEMBER_NO_TIME = 'sync_member_no_time'  # 成员无时间字段
    SYNC_MEMBER_ERROR = 'sync_member_error'      # 同步成员失败
    SYNC_NOT_JOINED = 'sync_not_joined'          # 未找到加入证据
    LEFT_OLD_TEAM = 'left_old_team'        # 退出旧 Team
    LEAVE_OLD_FAILED = 'leave_old_failed'  # 退出旧 Team 失败
    TRANSFERRED = 'transferred'            # 转移成功
    TRANSFER_FAILED = 'transfer_failed'    # 转移失败
    CANCELLED = 'cancelled'                # 取消租约
