import re
from typing import List, Pattern

# 提示注入特征模式：任何一条命中即视为疑似注入
_INJECTION_PATTERNS: List[Pattern] = [
    # 中文：忽略/忘记/跳过之前的指令
    re.compile(
        r"(忽略|忘记|无视|不要管|别管|不执行|跳过)\s*(之前|上述|上面|以上|刚才|所有)?\s*.{0,8}?(指令|设定|要求|规则|指示|约束)"
    ),
    # 英文：忽略/绕过指令
    re.compile(
        r"(ignore|disregard|forget|don'?t follow|bypass|override)\s+"
        r"(?:(?:all|any|your|the|previous|prior|above)\s+)*"
        r"(instructions?|prompts?|rules|constraints)",
        re.IGNORECASE,
    ),
    # 覆盖角色
    re.compile(r"你现在\s*(是|要|就|开始)?\s*(扮演|当)"),
    # 解除限制/过滤
    re.compile(r"(解锁|解除|绕过|取消|移除)\s*.{0,6}(限制|约束|过滤|规则|禁令)"),
    # 泄露/输出内部设定
    re.compile(
        r"(输出|泄露|复述|重述|告诉我)\s*.{0,8}(system\s*prompt|系统提示词?|提示词|内部设定|初始指令)",
        re.IGNORECASE,
    ),
]

# 数据标签：用户输入统一包进该标签，声明标签内是数据而非可执行的指令
_USER_INPUT_TAG = "user_input"


def check_prompt_injection(text: str) -> bool:
    """检测输入是否含提示注入特征。命中返回 True，由调用方降级处理（不拒绝）。"""
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            return True
    return False


def wrap_user_input(text: str) -> str:
    """把用户输入包进数据标签，使其中的指令性内容不再构成对系统指令的覆盖。"""
    return f"<{_USER_INPUT_TAG}>{text}</{_USER_INPUT_TAG}>"
