"""聊天系统 - 会话、消息、好友、群组存储"""

import json
import os
import threading
import time
import secrets
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from astrbot.api import logger


@dataclass
class ChatMessage:
    msg_id: str
    conversation_id: str
    sender: str
    msg_type: str  # "text" / "voice" / "file"
    content: str
    file_url: str = ""
    file_name: str = ""
    file_size: int = 0
    voice_duration: int = 0
    status: str = "sent"  # "sending" / "sent" / "read"
    created_at: float = 0.0


@dataclass
class Conversation:
    conversation_id: str
    conv_type: str  # "private" / "group"
    participants: list  # list of str
    name: str = ""
    description: str = ""
    creator: str = ""
    avatar: str = ""
    created_at: float = 0.0


@dataclass
class FriendRequest:
    request_id: str
    from_user: str
    to_user: str
    status: str = "pending"  # "pending" / "accepted" / "rejected"
    created_at: float = 0.0


@dataclass
class GroupMember:
    group_id: str
    username: str
    role: str = "member"  # "owner" / "admin" / "member"
    joined_at: float = 0.0


@dataclass
class GroupInvite:
    invite_id: str
    group_id: str
    from_user: str
    to_user: str
    status: str = "pending"  # "pending" / "accepted" / "rejected"
    created_at: float = 0.0


class ChatStore:
    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._lock = threading.Lock()

        self._conversations_path = os.path.join(data_dir, "dglab_conversations.json")
        self._messages_path = os.path.join(data_dir, "dglab_messages.json")
        self._friend_requests_path = os.path.join(
            data_dir, "dglab_friend_requests.json"
        )
        self._group_members_path = os.path.join(data_dir, "dglab_group_members.json")
        self._group_invites_path = os.path.join(data_dir, "dglab_group_invites.json")
        self._public_group_path = os.path.join(data_dir, "dglab_public_group.json")

        self._conversations: Dict[str, Conversation] = {}
        self._messages: Dict[str, ChatMessage] = {}
        self._friend_requests: Dict[str, FriendRequest] = {}
        self._group_members: Dict[str, GroupMember] = {}
        self._group_invites: Dict[str, GroupInvite] = {}
        self._public_group_id: Optional[str] = None

        os.makedirs(self._data_dir, exist_ok=True)
        self._load()

    # ─── 加载与保存 ───────────────────────────────────────────

    def _load(self):
        self._load_json(
            self._conversations_path,
            Conversation,
            self._conversations,
            "会话",
        )
        self._load_json(
            self._messages_path,
            ChatMessage,
            self._messages,
            "消息",
        )
        self._load_json(
            self._friend_requests_path,
            FriendRequest,
            self._friend_requests,
            "好友请求",
        )
        self._load_json(
            self._group_members_path,
            GroupMember,
            self._group_members,
            "群组成员",
        )
        self._load_json(
            self._group_invites_path,
            GroupInvite,
            self._group_invites,
            "群组邀请",
        )

        # 加载公共群组 ID
        if os.path.exists(self._public_group_path):
            try:
                with open(self._public_group_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._public_group_id = data.get("public_group_id")
            except Exception as e:
                logger.error(f"[DGLab Chat] 加载公共群组信息失败: {e}")

    def _load_json(self, path, cls, store, label):
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                with self._lock:
                    for key, val in data.items():
                        if isinstance(val, dict):
                            try:
                                store[key] = cls(**val)
                            except Exception as e:
                                logger.error(
                                    f"[DGLab Chat] 加载{label} {key} 失败: {e}"
                                )
            logger.info(f"[DGLab Chat] 已加载 {len(store)} 条{label}")
        except Exception as e:
            logger.error(f"[DGLab Chat] 加载{label}数据失败: {e}")

    def _save_json(self, path, store):
        try:
            with self._lock:
                data = {k: asdict(v) for k, v in store.items()}
            temp = path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        except Exception as e:
            logger.error(f"[DGLab Chat] 保存数据到 {path} 失败: {e}")

    def _save_conversations(self):
        self._save_json(self._conversations_path, self._conversations)

    def _save_messages(self):
        self._save_json(self._messages_path, self._messages)

    def _save_friend_requests(self):
        self._save_json(self._friend_requests_path, self._friend_requests)

    def _save_group_members(self):
        self._save_json(self._group_members_path, self._group_members)

    def _save_group_invites(self):
        self._save_json(self._group_invites_path, self._group_invites)

    def _save_public_group_id(self):
        try:
            data = {"public_group_id": self._public_group_id}
            temp = self._public_group_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self._public_group_path)
        except Exception as e:
            logger.error(f"[DGLab Chat] 保存公共群组信息失败: {e}")

    # ─── 会话 ─────────────────────────────────────────────────

    def create_private_conversation(self, user1: str, user2: str) -> str:
        """创建或返回已有的私聊会话。使用确定性 ID：排序用户名后用 '_' 连接。"""
        sorted_users = sorted([user1, user2])
        conv_id = "_".join(sorted_users)

        with self._lock:
            if conv_id in self._conversations:
                return conv_id

            conv = Conversation(
                conversation_id=conv_id,
                conv_type="private",
                participants=[user1, user2],
                created_at=time.time(),
            )
            self._conversations[conv_id] = conv

        self._save_conversations()
        logger.info(f"[DGLab Chat] 创建私聊会话: {conv_id}")
        return conv_id

    def create_group_conversation(
        self, name: str, description: str, creator: str, avatar: str = ""
    ) -> str:
        """创建群聊会话，自动将创建者添加为群主。"""
        conv_id = secrets.token_hex(8)

        with self._lock:
            conv = Conversation(
                conversation_id=conv_id,
                conv_type="group",
                participants=[creator],
                name=name,
                description=description,
                creator=creator,
                avatar=avatar,
                created_at=time.time(),
            )
            self._conversations[conv_id] = conv

            # 自动将创建者添加为群主
            member_key = f"{conv_id}:{creator}"
            self._group_members[member_key] = GroupMember(
                group_id=conv_id,
                username=creator,
                role="owner",
                joined_at=time.time(),
            )

        self._save_conversations()
        self._save_group_members()
        logger.info(f"[DGLab Chat] 创建群聊会话: {conv_id} ({name})")
        return conv_id

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """获取会话详情。"""
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if not conv:
                return None
            return asdict(conv)

    def get_user_conversations(self, username: str) -> List[dict]:
        """获取用户的所有会话（私聊和群聊）。
        私聊会话包含 other_user 信息，群聊会话包含 member_count。
        按最近消息时间排序（最近的在前）。"""
        with self._lock:
            user_convs = []
            for conv in self._conversations.values():
                if username in conv.participants:
                    d = asdict(conv)
                    if conv.conv_type == "private":
                        # 找到对方用户
                        other = [p for p in conv.participants if p != username]
                        d["other_user"] = other[0] if other else ""
                    elif conv.conv_type == "group":
                        # 统计成员数
                        count = sum(
                            1
                            for m in self._group_members.values()
                            if m.group_id == conv.conversation_id
                        )
                        d["member_count"] = count
                    user_convs.append(d)

        # 按最近消息时间排序
        def last_msg_time(conv_dict):
            conv_id = conv_dict["conversation_id"]
            latest = 0.0
            for msg in self._messages.values():
                if msg.conversation_id == conv_id and msg.created_at > latest:
                    latest = msg.created_at
            return latest

        user_convs.sort(key=last_msg_time, reverse=True)
        return user_convs

    def update_group_info(
        self,
        conversation_id: str,
        name: str,
        description: str,
        avatar: str,
        requester: str,
    ) -> bool:
        """更新群聊信息，仅创建者可操作。"""
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if not conv:
                return False
            if conv.conv_type != "group":
                return False
            if conv.creator != requester:
                return False
            conv.name = name
            conv.description = description
            conv.avatar = avatar

        self._save_conversations()
        return True

    def delete_conversation(self, conversation_id: str, requester: str) -> bool:
        """删除会话。群聊仅创建者可删除，私聊任一参与者可删除。"""
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if not conv:
                return False
            if conv.conv_type == "group" and conv.creator != requester:
                return False
            if conv.conv_type == "private" and requester not in conv.participants:
                return False

            # 删除会话
            del self._conversations[conversation_id]

            # 删除相关消息
            msg_ids_to_del = [
                mid
                for mid, msg in self._messages.items()
                if msg.conversation_id == conversation_id
            ]
            for mid in msg_ids_to_del:
                del self._messages[mid]

            # 如果是群聊，删除群成员
            if conv.conv_type == "group":
                member_keys_to_del = [
                    k
                    for k, m in self._group_members.items()
                    if m.group_id == conversation_id
                ]
                for k in member_keys_to_del:
                    del self._group_members[k]

        self._save_conversations()
        self._save_messages()
        if conv.conv_type == "group":
            self._save_group_members()
        logger.info(f"[DGLab Chat] 会话 {conversation_id} 已被 {requester} 删除")
        return True

    # ─── 消息 ─────────────────────────────────────────────────

    def send_message(
        self,
        conversation_id: str,
        sender: str,
        msg_type: str,
        content: str,
        file_url: str = "",
        file_name: str = "",
        file_size: int = 0,
        voice_duration: int = 0,
    ) -> Optional[str]:
        """发送消息。验证发送者是否为会话参与者。返回 msg_id。"""
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if not conv:
                return None
            if sender not in conv.participants:
                return None

        msg_id = secrets.token_hex(8)
        msg = ChatMessage(
            msg_id=msg_id,
            conversation_id=conversation_id,
            sender=sender,
            msg_type=msg_type,
            content=content,
            file_url=file_url,
            file_name=file_name,
            file_size=file_size,
            voice_duration=voice_duration,
            status="sent",
            created_at=time.time(),
        )

        with self._lock:
            self._messages[msg_id] = msg

        self._save_messages()
        return msg_id

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before: Optional[float] = None,
        requester: str = "",
    ) -> List[dict]:
        """获取会话消息。按 created_at 降序排列，限制数量。
        如果提供 before，只返回该时间之前的消息。
        将非 requester 发送的消息标记为已读。"""
        with self._lock:
            msgs = [
                msg
                for msg in self._messages.values()
                if msg.conversation_id == conversation_id
            ]

        # 时间过滤
        if before is not None:
            msgs = [m for m in msgs if m.created_at < before]

        # 按时间降序排序
        msgs.sort(key=lambda m: m.created_at, reverse=True)

        # 限制数量
        msgs = msgs[:limit]

        # 标记非 requester 发送的消息为已读
        marked = False
        with self._lock:
            for msg in msgs:
                if msg.sender != requester and msg.status != "read":
                    msg.status = "read"
                    marked = True

        if marked:
            self._save_messages()

        return [asdict(m) for m in msgs]

    def mark_messages_read(self, conversation_id: str, username: str) -> int:
        """将会话中所有未读消息标记为已读（非 username 发送的消息）。
        返回标记的消息数量。"""
        count = 0
        with self._lock:
            for msg in self._messages.values():
                if (
                    msg.conversation_id == conversation_id
                    and msg.sender != username
                    and msg.status != "read"
                ):
                    msg.status = "read"
                    count += 1

        if count > 0:
            self._save_messages()
        return count

    # ─── 好友 ─────────────────────────────────────────────────

    def send_friend_request(self, from_user: str, to_user: str) -> Tuple[bool, str]:
        """发送好友请求。检查：不能加自己、不能重复发送、不能加已有好友。"""
        if from_user == to_user:
            return False, "不能添加自己为好友"

        with self._lock:
            # 检查是否有待处理的请求
            for req in self._friend_requests.values():
                if (
                    req.from_user == from_user
                    and req.to_user == to_user
                    and req.status == "pending"
                ):
                    return False, "已发送过好友请求，请等待对方确认"

            # 检查是否已是好友
            sorted_users = sorted([from_user, to_user])
            conv_id = "_".join(sorted_users)
            if conv_id in self._conversations:
                return False, "你们已经是好友了"

        request_id = secrets.token_hex(8)
        req = FriendRequest(
            request_id=request_id,
            from_user=from_user,
            to_user=to_user,
            status="pending",
            created_at=time.time(),
        )

        with self._lock:
            self._friend_requests[request_id] = req

        self._save_friend_requests()
        logger.info(f"[DGLab Chat] 好友请求: {from_user} -> {to_user}")
        return True, "好友请求已发送"

    def get_friend_requests(self, username: str) -> List[dict]:
        """获取收到的待处理好友请求。"""
        with self._lock:
            return [
                asdict(req)
                for req in self._friend_requests.values()
                if req.to_user == username and req.status == "pending"
            ]

    def get_sent_friend_requests(self, username: str) -> List[dict]:
        """获取发出的待处理好友请求。"""
        with self._lock:
            return [
                asdict(req)
                for req in self._friend_requests.values()
                if req.from_user == username and req.status == "pending"
            ]

    def accept_friend_request(self, request_id: str) -> Tuple[bool, str]:
        """接受好友请求，自动创建私聊会话。"""
        with self._lock:
            req = self._friend_requests.get(request_id)
            if not req:
                return False, "好友请求不存在"
            if req.status != "pending":
                return False, "好友请求已处理"

            req.status = "accepted"
            from_user = req.from_user
            to_user = req.to_user

        self._save_friend_requests()

        # 创建私聊会话
        conv_id = self.create_private_conversation(from_user, to_user)
        logger.info(
            f"[DGLab Chat] 好友请求已接受: {from_user} <-> {to_user} (会话: {conv_id})"
        )
        return True, "已添加好友"

    def reject_friend_request(self, request_id: str) -> Tuple[bool, str]:
        """拒绝好友请求。"""
        with self._lock:
            req = self._friend_requests.get(request_id)
            if not req:
                return False, "好友请求不存在"
            if req.status != "pending":
                return False, "好友请求已处理"

            req.status = "rejected"

        self._save_friend_requests()
        return True, "已拒绝好友请求"

    def get_friends(self, username: str) -> List[dict]:
        """获取好友列表，返回 [{username, conversation_id}]。"""
        friends = []
        with self._lock:
            for conv in self._conversations.values():
                if conv.conv_type == "private" and username in conv.participants:
                    other = [p for p in conv.participants if p != username]
                    if other:
                        friends.append(
                            {
                                "username": other[0],
                                "conversation_id": conv.conversation_id,
                            }
                        )
        return friends

    def remove_friend(self, username: str, friend_username: str) -> bool:
        """移除好友关系并删除私聊会话。"""
        sorted_users = sorted([username, friend_username])
        conv_id = "_".join(sorted_users)

        with self._lock:
            conv = self._conversations.get(conv_id)
            if not conv:
                return False
            if username not in conv.participants:
                return False

            # 删除会话
            del self._conversations[conv_id]

            # 删除相关消息
            msg_ids_to_del = [
                mid
                for mid, msg in self._messages.items()
                if msg.conversation_id == conv_id
            ]
            for mid in msg_ids_to_del:
                del self._messages[mid]

        self._save_conversations()
        self._save_messages()
        logger.info(f"[DGLab Chat] 好友关系已移除: {username} <-> {friend_username}")
        return True

    # ─── 群组 ─────────────────────────────────────────────────

    def get_group_members(self, group_id: str) -> List[dict]:
        """获取群组所有成员。"""
        with self._lock:
            return [
                asdict(m)
                for m in self._group_members.values()
                if m.group_id == group_id
            ]

    def invite_to_group(
        self, group_id: str, inviter: str, invitee: str
    ) -> Tuple[bool, str]:
        """邀请用户加入群组。仅群主/管理员可邀请，不能邀请已有成员，不能重复邀请。"""
        with self._lock:
            # 检查邀请者权限
            inviter_key = f"{group_id}:{inviter}"
            inviter_member = self._group_members.get(inviter_key)
            if not inviter_member:
                return False, "你不是该群组成员"
            if inviter_member.role not in ("owner", "admin"):
                return False, "仅群主或管理员可以邀请"

            # 检查被邀请者是否已是成员
            invitee_key = f"{group_id}:{invitee}"
            if invitee_key in self._group_members:
                return False, "该用户已是群组成员"

            # 检查是否有待处理的邀请
            for inv in self._group_invites.values():
                if (
                    inv.group_id == group_id
                    and inv.to_user == invitee
                    and inv.status == "pending"
                ):
                    return False, "已发送过邀请，请等待对方确认"

        invite_id = secrets.token_hex(8)
        invite = GroupInvite(
            invite_id=invite_id,
            group_id=group_id,
            from_user=inviter,
            to_user=invitee,
            status="pending",
            created_at=time.time(),
        )

        with self._lock:
            self._group_invites[invite_id] = invite

        self._save_group_invites()
        logger.info(f"[DGLab Chat] 群组邀请: {inviter} 邀请 {invitee} 加入 {group_id}")
        return True, "邀请已发送"

    def get_group_invites(self, username: str) -> List[dict]:
        """获取用户的待处理群组邀请。"""
        with self._lock:
            return [
                asdict(inv)
                for inv in self._group_invites.values()
                if inv.to_user == username and inv.status == "pending"
            ]

    def accept_group_invite(self, invite_id: str) -> Tuple[bool, str]:
        """接受群组邀请，将用户添加为群成员和会话参与者。"""
        with self._lock:
            invite = self._group_invites.get(invite_id)
            if not invite:
                return False, "邀请不存在"
            if invite.status != "pending":
                return False, "邀请已处理"

            invite.status = "accepted"
            group_id = invite.group_id
            username = invite.to_user

            # 添加为群成员
            member_key = f"{group_id}:{username}"
            self._group_members[member_key] = GroupMember(
                group_id=group_id,
                username=username,
                role="member",
                joined_at=time.time(),
            )

            # 添加为会话参与者
            conv = self._conversations.get(group_id)
            if conv and username not in conv.participants:
                conv.participants.append(username)

        self._save_group_invites()
        self._save_group_members()
        self._save_conversations()
        logger.info(f"[DGLab Chat] {username} 已加入群组 {group_id}")
        return True, "已加入群组"

    def reject_group_invite(self, invite_id: str) -> Tuple[bool, str]:
        """拒绝群组邀请。"""
        with self._lock:
            invite = self._group_invites.get(invite_id)
            if not invite:
                return False, "邀请不存在"
            if invite.status != "pending":
                return False, "邀请已处理"

            invite.status = "rejected"

        self._save_group_invites()
        return True, "已拒绝群组邀请"

    def remove_group_member(self, group_id: str, username: str, remover: str) -> bool:
        """移除群组成员。仅群主/管理员可操作，不能移除群主。"""
        with self._lock:
            # 检查操作者权限
            remover_key = f"{group_id}:{remover}"
            remover_member = self._group_members.get(remover_key)
            if not remover_member:
                return False
            if remover_member.role not in ("owner", "admin"):
                return False

            # 不能移除群主
            target_key = f"{group_id}:{username}"
            target_member = self._group_members.get(target_key)
            if not target_member:
                return False
            if target_member.role == "owner":
                return False

            # 移除成员
            del self._group_members[target_key]

            # 从会话参与者中移除
            conv = self._conversations.get(group_id)
            if conv and username in conv.participants:
                conv.participants.remove(username)

        self._save_group_members()
        self._save_conversations()
        logger.info(f"[DGLab Chat] {username} 已被 {remover} 从群组 {group_id} 移除")
        return True

    def leave_group(self, group_id: str, username: str) -> bool:
        """离开群组。群主不能离开。"""
        with self._lock:
            member_key = f"{group_id}:{username}"
            member = self._group_members.get(member_key)
            if not member:
                return False
            if member.role == "owner":
                return False

            # 移除成员
            del self._group_members[member_key]

            # 从会话参与者中移除
            conv = self._conversations.get(group_id)
            if conv and username in conv.participants:
                conv.participants.remove(username)

        self._save_group_members()
        self._save_conversations()
        logger.info(f"[DGLab Chat] {username} 已离开群组 {group_id}")
        return True

    # ─── 搜索 ─────────────────────────────────────────────────

    def search_users(
        self, query: str, current_user: str, user_store=None, limit: int = 20
    ) -> List[dict]:
        """按用户名模糊搜索用户，排除当前用户。返回 [{username, nickname, avatar}]。"""
        if user_store is None:
            return []

        results = []
        q = query.lower()
        with self._lock:
            pass  # 不需要访问 chat store 的锁

        # 通过 user_store 获取所有用户
        all_users = user_store.list_all_users()
        for u in all_users:
            uname = u.get("username", "")
            if uname == current_user:
                continue
            if q in uname.lower():
                user_info = user_store.get_user(uname)
                results.append(
                    {
                        "username": uname,
                        "nickname": getattr(user_info, "nickname", "")
                        if user_info
                        else "",
                        "avatar": getattr(user_info, "avatar", "") if user_info else "",
                    }
                )
                if len(results) >= limit:
                    break

        return results

    # ─── 默认公共群组 ─────────────────────────────────────────

    def ensure_public_group(self, user_store) -> None:
        """创建"集思广益交友群"公共群组（如不存在），并将所有现有用户添加为成员。"""
        with self._lock:
            if self._public_group_id and self._public_group_id in self._conversations:
                return

        # 创建公共群组
        group_id = self.create_group_conversation(
            name="集思广益交友群",
            description="欢迎各位加入，畅所欲言！",
            creator="system",
            avatar="",
        )

        with self._lock:
            self._public_group_id = group_id
        self._save_public_group_id()

        # 将所有现有用户添加为成员
        if user_store:
            all_users = user_store.list_all_users()
            for u in all_users:
                uname = u.get("username", "")
                if not uname:
                    continue
                with self._lock:
                    member_key = f"{group_id}:{uname}"
                    if member_key not in self._group_members:
                        self._group_members[member_key] = GroupMember(
                            group_id=group_id,
                            username=uname,
                            role="member",
                            joined_at=time.time(),
                        )
                    conv = self._conversations.get(group_id)
                    if conv and uname not in conv.participants:
                        conv.participants.append(uname)

            self._save_group_members()
            self._save_conversations()

        logger.info(f"[DGLab Chat] 公共群组已创建: {group_id}")

    def add_user_to_public_group(self, username: str, user_store=None) -> None:
        """将新注册用户添加到公共群组。"""
        with self._lock:
            if not self._public_group_id:
                return
            group_id = self._public_group_id

            member_key = f"{group_id}:{username}"
            if member_key in self._group_members:
                return

            self._group_members[member_key] = GroupMember(
                group_id=group_id,
                username=username,
                role="member",
                joined_at=time.time(),
            )

            conv = self._conversations.get(group_id)
            if conv and username not in conv.participants:
                conv.participants.append(username)

        self._save_group_members()
        self._save_conversations()
        logger.info(f"[DGLab Chat] {username} 已添加到公共群组")
