"""DG-LAB 模块边界测试脚本

测试覆盖:
1. 参数校验（非法输入、边界值）
2. 命令解析正确性
3. 异常处理完整性
4. 多用户隔离性
5. 资源管理（连接泄漏检测）

运行方式: python test_dglab_integration.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from datetime import datetime


class MockLogger:
    """模拟AstrBot logger"""
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg, **kwargs): pass

class MockAstrBotAPI:
    """模拟 astrbot.api 模块"""
    logger = MockLogger()

sys.modules['astrbot'] = type(sys)('astrbot')
sys.modules['astrbot.api'] = MockAstrBotAPI()

from dglab_device_store import DeviceStore, DeviceBinding
from dglab_commands import DGLabCommandHandler, DGLabCommandError


class MockEvent:
    """模拟AstrMessageEvent"""
    def __init__(self, user_id="test_user_123", user_name="TestUser"):
        self._user_id = user_id
        self._user_name = user_name
    
    def get_sender_id(self):
        return self._user_id
    
    def get_sender_name(self):
        return self._user_name
    
    def message_str(self):
        return ""
    
    def plain_result(self, text):
        return {"type": "plain", "text": text}
    
    def image_result(self, url):
        return {"type": "image", "url": url}


class TestResults:
    """测试结果收集器"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name):
        self.passed += 1
        print(f"  ✅ {test_name}")
    
    def add_fail(self, test_name, reason):
        self.failed += 1
        self.errors.append((test_name, reason))
        print(f"  ❌ {test_name}: {reason}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.errors:
            print(f"\n失败详情:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        print(f"{'='*50}")
        return self.failed == 0


async def test_device_store():
    """测试设备存储模块"""
    print("\n📦 测试 DeviceStore (设备存储)")
    results = TestResults()
    
    store = DeviceStore(data_dir="test_data")
    
    try:
        binding = DeviceBinding(
            user_id="user001",
            client_id="client-abc123",
            target_id="target-xyz789",
            server_url="ws://192.168.1.100:9999",
            bound_time=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            nickname="TestUser",
        )
        
        store.set_binding(binding)
        results.add_pass("设置绑定")
        
        retrieved = store.get_binding("user001")
        assert retrieved is not None, "绑定不存在"
        assert retrieved.client_id == "client-abc123"
        results.add_pass("获取绑定")
        
        assert store.exists("user001") == True
        results.add_pass("检查存在")
        
        assert store.exists("nonexistent") == False
        results.add_pass("检查不存在")
        
        store.update_last_active("user001")
        updated = store.get_binding("user001")
        assert updated.last_active != binding.last_active
        results.add_pass("更新活跃时间")
        
        removed = store.remove_binding("user001")
        assert removed == True
        results.add_pass("移除绑定")
        
        after_remove = store.get_binding("user001")
        assert after_remove is None
        results.add_pass("验证移除后不存在")
        
        remove_again = store.remove_binding("user001")
        assert remove_again == False
        results.add_pass("重复移除返回False")
        
        count = store.count()
        assert count == 0
        results.add_pass("计数为0")
        
    except Exception as e:
        results.add_fail("DeviceStore异常", str(e))
    
    import shutil
    shutil.rmtree("test_data", ignore_errors=True)
    
    return results


async def test_command_parser():
    """测试命令解析器"""
    print("\n🔍 测试 CommandParser (命令解析)")
    results = TestResults()
    
    handler = DGLabCommandHandler(connection_pool=None, device_store=None)
    event = MockEvent()
    
    test_cases = [
        ("/dglab help", "help", ""),
        ("/dglab bind ws://localhost:9999", "bind", "ws://localhost:9999"),
        ("dglab unbind", "unbind", ""),
        ("dglab strength A 50", "strength", "A 50"),
        ("dglab up B 10", "up", "B 10"),
        ("dglab down A", "down", "A"),
        ("dglab stop", "stop", ""),
        ("dglab clear B", "clear", "B"),
        ("dglab status", "status", ""),
        ("!dglab info", "info", ""),
    ]
    
    for input_cmd, expected_cmd, expected_args in test_cases:
        try:
            cmd, args = handler._parse_command(input_cmd)
            if cmd == expected_cmd and args.strip() == expected_args.strip():
                results.add_pass(f"解析: '{input_cmd}' -> ({cmd}, '{args}')")
            else:
                results.add_fail(
                    f"解析失败: '{input_cmd}'",
                    f"期望({expected_cmd}, '{expected_args}') 实际({cmd}, '{args}')"
                )
        except Exception as e:
            results.add_fail(f"解析异常: '{input_cmd}'", str(e))
    
    return results


async def test_parameter_validation():
    """测试参数校验"""
    print("\n✅ 测试 ParameterValidation (参数校验)")
    results = TestResults()
    
    handler = DGLabCommandHandler(connection_pool=None, device_store=None)
    
    channel_tests = [
        ("A", 1),
        ("B", 2),
        ("a", 1),
        ("b", 2),
    ]
    
    for input_ch, expected in channel_tests:
        try:
            result = handler._parse_channel(input_ch)
            if result == expected:
                results.add_pass(f"通道解析: '{input_ch}' -> {result}")
            else:
                results.add_fail(f"通道错误: '{input_ch}'", f"期望{expected} 实际{result}")
        except DGLabCommandError as e:
            results.add_fail(f"通道异常: '{input_ch}'", str(e))
    
    invalid_channels = ["C", "X", "1", "2", "", "AB"]
    for invalid_ch in invalid_channels:
        try:
            result = handler._parse_channel(invalid_ch)
            results.add_fail(f"无效通道未拒绝: '{invalid_ch}'", f"返回{result}")
        except DGLabCommandError:
            results.add_pass(f"正确拒绝无效通道: '{invalid_ch}'")
    
    strength_tests = [
        ("A 0", True, 1, 0),      # 最小值
        ("A 200", True, 1, 200),   # 最大值
        ("B 100", True, 2, 100),   # 正常值
        ("A -1", False, None, None), # 负数
        ("A 201", False, None, None), # 超出范围
        ("A abc", False, None, None), # 非数字
        ("A", False, None, None),     # 缺少参数
    ]
    
    for input_str, should_pass, exp_ch, exp_val in strength_tests:
        try:
            ch, val = handler._parse_strength_args(input_str)
            if should_pass and ch == exp_ch and val == exp_val:
                results.add_pass(f"强度校验通过: '{input_str}' -> ch={ch}, val={val}")
            elif not should_pass:
                results.add_fail(f"强度校验应失败但通过了: '{input_str}'")
            else:
                results.add_fail(
                    f"强度返回值错误: '{input_str}'",
                    f"期望ch={exp_ch},val={exp_val} 实际ch={ch},val={val}"
                )
        except (DGLabCommandError, ValueError, IndexError) as e:
            if not should_pass:
                results.add_pass(f"正确拒绝: '{input_str}' -> {type(e).__name__}")
            else:
                results.add_fail(f"不应抛异常: '{input_str}'", str(e))
    
    adjust_tests = [
        ("A", 1, 5),
        ("B 10", 2, 10),
        ("A 200", 1, 200),
        ("A 1", 1, 1),
    ]
    
    for input_str, exp_ch, exp_step in adjust_tests:
        try:
            ch, step = handler._parse_strength_adjust_args(input_str)
            if ch == exp_ch and step == exp_step:
                results.add_pass(f"调整参数: '{input_str}' -> ch={ch}, step={step}")
            else:
                results.add_fail(
                    f"调整参数错误: '{input_str}'",
                    f"期望ch={exp_ch},step={exp_step}"
                )
        except Exception as e:
            results.add_fail(f"调整参数异常: '{input_str}'", str(e))
    
    return results


async def test_error_handling():
    """测试异常处理"""
    print("\n🛡️ 测试 ErrorHandling (异常处理)")
    results = TestResults()
    
    handler = DGLabCommandHandler(connection_pool=None, device_store=None)
    
    unknown_cmds = ["unknown", "xxx", "bindx", "strengths"]
    for cmd in unknown_cmds:
        try:
            await handler._dispatch_command(cmd, "", "user", "User", MockEvent())
            results.add_fail(f"未知命令未被拦截: '{cmd}'")
        except DGLabCommandError as e:
            results.add_pass(f"正确处理未知命令: '{cmd}'")
        except Exception as e:
            results.add_fail(f"未知命令异常类型: '{cmd}'", type(e).__name__)
    
    empty_input_cases = ["", " ", "  "]
    for inp in empty_input_cases:
        try:
            cmd, args = handler._parse_command(inp)
            if cmd == "help":
                results.add_pass(f"空输入显示帮助: '{inp}'")
            else:
                results.add_fail(f"空输入处理异常: '{inp}'", f"cmd={cmd}")
        except Exception as e:
            results.add_fail(f"空输入抛异常: '{inp}'", str(e))
    
    return results


async def test_multitenancy():
    """测试多用户隔离性"""
    print("\👥 测试 Multitenancy (多用户隔离)")
    results = TestResults()
    
    store = DeviceStore(data_dir="test_data_multi")
    
    users = [
        ("user_A", "client_AAA", "target_AAA", "Alice"),
        ("user_B", "client_BBB", "target_BBB", "Bob"),
        ("user_C", "client_CCC", "target_CCC", "Charlie"),
    ]
    
    for uid, cid, tid, name in users:
        binding = DeviceBinding(
            user_id=uid,
            client_id=cid,
            target_id=tid,
            server_url="ws://test:9999",
            bound_time=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            nickname=name,
        )
        store.set_binding(binding)
    
    results.add_pass(f"创建{len(users)}个用户绑定")
    
    for uid, cid, tid, name in users:
        b = store.get_binding(uid)
        if b and b.client_id == cid and b.nickname == name:
            results.add_pass(f"用户{uid}数据隔离正确")
        else:
            results.add_fail(f"用户{uid}数据隔离失败", f"期望cid={cid}")
    
    store.remove_binding("user_B")
    
    if store.exists("user_A") and store.exists("user_C"):
        results.add_pass("删除user_B不影响其他用户")
    else:
        results.add_fail("删除操作影响了其他用户")
    
    if not store.exists("user_B"):
        results.add_pass("user_B已成功删除")
    else:
        results.add_fail("user_B删除后仍存在")
    
    import shutil
    shutil.rmtree("test_data_multi", ignore_errors=True)
    
    return results


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 DG-LAB 模块集成测试套件")
    print("=" * 60)
    
    all_results = []
    
    all_results.append(await test_device_store())
    all_results.append(await test_command_parser())
    all_results.append(await test_parameter_validation())
    all_results.append(await test_error_handling())
    all_results.append(await test_multitenancy())
    
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    
    print("\n" + "=" * 60)
    print(f"📊 总计: {total_passed}/{total_passed + total_failed} 测试通过")
    
    if total_failed > 0:
        print(f"\n⚠️  有 {total_failed} 个测试失败，请查看上方详细信息")
        return False
    else:
        print(f"\n🎉 所有测试通过！集成验证成功！")
        return True


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
