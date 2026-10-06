#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poker Squares 接龙（扑克方块 solitaire）

玩法：标准 52 张牌洗牌，每次发 1 张，玩家把它放到 5x5 网格的任意空格。
25 张放完后，每行每列各组成一手 5 张牌，按美式计分（American point system）
计分，10 手总和即最终得分。目标：尽可能拿高分（理论最高 500）。

计分表（美式）：
    皇家同花顺 100 / 同花顺 75 / 四条 50 / 葫芦 25 / 同花 20 /
    顺子 15 / 三条 10 / 两对 5 / 一对 2 / 高牌 0

只用标准库：argparse / sys / random / secrets。
"""

import argparse
import random
import secrets
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# 牌
# ---------------------------------------------------------------------------
# 牌 = (点数, 花色)，点数 2..14（11=J,12=Q,13=K,14=A），花色 0..3（黑桃/红桃/方块/梅花）
RANK_LABEL = {r: str(r) for r in range(2, 11)}
RANK_LABEL.update({11: "J", 12: "Q", 13: "K", 14: "A"})
SUITS = ["♠", "♥", "♦", "♣"]
RED_SUITS = (1, 2)  # ♥ ♦


def new_deck():
    """标准 52 张牌（未洗牌）。"""
    return [(rank, suit) for suit in range(4) for rank in range(2, 15)]


def shuffled_deck(seed=None):
    """洗牌后的牌堆。seed 为 None 时用 secrets 真随机，否则用 seed 可复现。"""
    deck = new_deck()
    if seed is None:
        secrets.SystemRandom().shuffle(deck)
    else:
        random.Random(seed).shuffle(deck)
    return deck


# ---------------------------------------------------------------------------
# 计分
# ---------------------------------------------------------------------------
# 美式计分（American point system）
HAND_NAMES = {
    100: "皇家同花顺",
    75: "同花顺",
    50: "四条",
    25: "葫芦",
    20: "同花",
    15: "顺子",
    10: "三条",
    5: "两对",
    2: "一对",
    0: "高牌",
}


def hand_score(cards):
    """给一手 5 张牌打分。cards 为 [(点数, 花色)] 列表。"""
    if len(cards) != 5:
        raise ValueError("一手牌必须是 5 张")
    ranks = sorted(r for r, _ in cards)
    suits = [s for _, s in cards]
    counts = sorted(Counter(ranks).values(), reverse=True)

    is_flush = len(set(suits)) == 1
    distinct = sorted(set(ranks))
    is_straight = (
        len(distinct) == 5
        and (distinct[-1] - distinct[0] == 4 or distinct == [2, 3, 4, 5, 14])
    )

    if is_flush and is_straight:
        # T,J,Q,K,A 同花 = 皇家同花顺（100），其余同花顺 75
        return 100 if distinct[0] == 10 else 75
    if counts[0] == 4:
        return 50
    if counts == [3, 2]:
        return 25
    if is_flush:
        return 20
    if is_straight:
        return 15
    if counts[0] == 3:
        return 10
    if counts == [2, 2, 1]:
        return 5
    if counts[0] == 2:
        return 2
    return 0


def hand_name(cards):
    """一手牌的中文名。"""
    return HAND_NAMES[hand_score(cards)]


# ---------------------------------------------------------------------------
# 网格
# ---------------------------------------------------------------------------
class Grid:
    def __init__(self):
        self.cells = [[None] * 5 for _ in range(5)]

    def empty_cells(self):
        return [(r, c) for r in range(5) for c in range(5) if self.cells[r][c] is None]

    def full(self):
        return not self.empty_cells()

    def place(self, row, col, card):
        """把牌放到 (row, col)，0-based。非法位置/已被占用抛 ValueError。"""
        if not (0 <= row < 5 and 0 <= col < 5):
            raise ValueError(f"位置超出范围：行列必须是 1-5，收到 ({row + 1},{col + 1})")
        if self.cells[row][col] is not None:
            raise ValueError(f"({row + 1},{col + 1}) 已经有牌了")
        self.cells[row][col] = card

    def rows(self):
        return [list(r) for r in self.cells]

    def cols(self):
        return [[self.cells[r][c] for r in range(5)] for c in range(5)]

    def score(self):
        """10 手（5 行 + 5 列）总分。网格未满时抛 ValueError。"""
        if not self.full():
            raise ValueError("网格未放满，不能计分")
        return sum(hand_score(line) for line in self.rows() + self.cols())

    def breakdown(self):
        """返回 [(标签, 中文牌型, 分数)]，5 行 + 5 列。"""
        out = []
        for i, line in enumerate(self.rows()):
            s = hand_score(line)
            out.append((f"行{i + 1}", HAND_NAMES[s], s))
        for i, line in enumerate(self.cols()):
            s = hand_score(line)
            out.append((f"列{i + 1}", HAND_NAMES[s], s))
        return out


# ---------------------------------------------------------------------------
# 显示
# ---------------------------------------------------------------------------
_ANSI_RED = "\033[31m"
_ANSI_RESET = "\033[0m"


def card_str(card, color=True):
    r, s = card
    text = f"{RANK_LABEL[r]:>2}{SUITS[s]}"
    if color and s in RED_SUITS:
        return f"{_ANSI_RED}{text}{_ANSI_RESET}"
    return text


def render(grid, color=True):
    lines = ["     1    2    3    4    5"]
    for r in range(5):
        row = []
        for c in range(5):
            card = grid.cells[r][c]
            row.append(card_str(card, color) if card else "  · ")
        lines.append(f"  {r + 1} " + " ".join(row))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 贪心机器人（--auto）
# ---------------------------------------------------------------------------
def line_potential(cards):
    """一条行/列的潜力启发值（cards 为已放入的牌，<=5 张）。"""
    cards = [c for c in cards if c is not None]
    if not cards:
        return 0.0
    n = len(cards)
    v = 0.0
    counts = Counter(r for r, _ in cards)
    for cnt in counts.values():
        if cnt == 2:
            v += 1.5
        elif cnt == 3:
            v += 5.0
        elif cnt >= 4:
            v += 14.0
    if len({s for _, s in cards}) == 1:
        v += 2.0 * n  # 同花潜力
    distinct = sorted(counts)
    if len(distinct) == n and distinct[-1] - distinct[0] <= 4:
        v += 1.0 * n  # 顺子潜力
    return v


def choose_cell(grid, card):
    """贪心：把牌放到（行潜力 + 列潜力）最大的空格。"""
    best, best_val = None, -1.0
    for r, c in grid.empty_cells():
        grid.cells[r][c] = card
        val = line_potential(grid.cells[r]) + line_potential(
            [grid.cells[i][c] for i in range(5)]
        )
        grid.cells[r][c] = None
        if val > best_val:
            best, best_val = (r, c), val
    return best


# ---------------------------------------------------------------------------
# 游戏流程
# ---------------------------------------------------------------------------
def play_auto(deck, verbose=True):
    grid = Grid()
    for i, card in enumerate(deck[:25], 1):
        r, c = choose_cell(grid, card)
        grid.place(r, c, card)
        if verbose:
            print(f"第{i:2d}张 {card_str(card)} → ({r + 1},{c + 1})")
    return grid


def play_interactive(deck):
    grid = Grid()
    color = sys.stdout.isatty()
    for i, card in enumerate(deck[:25], 1):
        while True:
            print(render(grid, color))
            print(f"\n第 {i}/25 张：{card_str(card, color)}")
            try:
                s = input("放到哪？输入「行 列」(1-5)，如 2 3；q 退出：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                return None
            if s.lower() in ("q", "quit", "退出", "exit"):
                print("已退出。")
                return None
            parts = s.replace(",", " ").split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                r, c = int(parts[0]) - 1, int(parts[1]) - 1
                try:
                    grid.place(r, c, card)
                    break
                except ValueError as e:
                    print(f"放不下：{e}")
            else:
                print("输入格式不对：请输入两个 1-5 的数字，如 2 3")
    return grid


def print_result(grid):
    color = sys.stdout.isatty()
    print()
    print(render(grid, color))
    print()
    print("── 计分明细 ──")
    total = 0
    for label, name, s in grid.breakdown():
        print(f"  {label}：{name}（{s} 分）")
        total += s
    print(f"\n总分：{total} 分")
    return total


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Poker Squares 接龙：5x5 网格逐张放牌，行列按美式扑克计分。"
    )
    parser.add_argument("--seed", type=int, default=None, help="随机种子（可复现牌序）")
    parser.add_argument("--auto", action="store_true", help="贪心机器人自动玩一局")
    args = parser.parse_args(argv)

    deck = shuffled_deck(args.seed)
    if args.auto:
        print("🤖 贪心机器人自动开局…\n")
        grid = play_auto(deck)
    else:
        print("🃏 Poker Squares 接龙")
        print("规则：每次发 1 张牌，放到 5x5 网格任意空格；25 张放完后，")
        print("每行每列按美式计分：皇家同花顺100 / 同花顺75 / 四条50 / 葫芦25 /")
        print("同花20 / 顺子15 / 三条10 / 两对5 / 一对2，加总即总分。\n")
        grid = play_interactive(deck)

    if grid is None:
        return 1
    print_result(grid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
