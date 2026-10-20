"""Write the hand-made memory evaluation cases (synthetic, never used for training) to JSONL files.

Every case uses the same "today", Tuesday 2026-10-20, so expected dates are fixed.
Run: python -m training.rewrite.memory_eval.build_cases
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TODAY = "2026-10-20"


def P(name):
    return {"kind": "person", "content": name}


def T(name):
    return {"kind": "term", "content": name}


def E(content, time):
    return {"kind": "event", "content": content, "time": time}


def F(content):
    return {"kind": "fact", "content": content}


# (text, expected items). An event's "time" lists accepted spellings: the words said or the resolved date.
EXTRACT = [
    ("周三下午三点开评审会，记得带电脑。", [E("评审会", ["周三下午三点", "10月21日"])]),
    ("王书涵明天上午十点来面试，你接待一下。", [P("王书涵"), E("王书涵面试", ["明天上午十点", "10月21日"])]),
    ("北极星项目下周一上线，大家把测试做完。", [T("北极星项目"), E("北极星项目上线", ["下周一", "10月26日"])]),
    ("好的，收到，谢谢！", []),
    ("哈哈今天天气真好。", []),
    ("我对芒果过敏，聚餐别点芒果。", [F("对芒果过敏")]),
    ("周五晚上七点和欧阳小雨在海底捞吃饭。", [P("欧阳小雨"), E("和欧阳小雨吃饭", ["周五晚上七点", "10月23日"])]),
    ("客户是星河科技，对接人叫李铭。", [T("星河科技"), P("李铭")]),
    ("房租每个月十五号交。", [F("房租每月十五号交")]),
    ("我先去吃个饭，一会儿回来。", []),
    ("10月28日之前把年度报告交给财务部。", [E("交年度报告", ["10月28日"])]),
    ("下周三的周会取消了。", [E("周会取消", ["下周三", "10月28日"])]),
    ("新来的实习生叫陈子墨，在设计组。", [P("陈子墨")]),
    ("我们用的数据库是PostgreSQL，别用MySQL。", [T("PostgreSQL")]),
    ("明天早上八点的高铁去上海，G102次。", [E("高铁去上海", ["明天早上八点", "10月21日"]), T("G102")]),
    ("太好了，终于下班了！", []),
    ("我家的WiFi密码贴在冰箱上。", [F("WiFi密码贴在冰箱上")]),
    ("张总说季度目标改成两百万。", [P("张总"), F("季度目标改成两百万")]),
    ("今天下午四点给牙医打电话改预约。", [E("给牙医打电话改预约", ["今天下午四点", "10月20日"])]),
    ("嗯嗯，好的，没问题。", []),
    ("Meeting with Sarah Chen on Thursday at 2pm about the Q4 budget.",
     [P("Sarah Chen"), E("Meeting with Sarah Chen", ["Thursday at 2pm", "10月22日"])]),
    ("Our staging server is called Atlas.", [T("Atlas")]),
    ("Thanks, see you tomorrow!", []),
    ("The deadline for the grant application is November 3rd.", [E("Grant application deadline", ["November 3rd", "11月3日"])]),
    ("I prefer meetings in the morning.", [F("Prefers morning meetings")]),
    ("每周一早上九点开部门例会。", [E("部门例会", ["每周一早上九点"])]),
    ("妈妈的生日是腊月初八。", [F("妈妈的生日是腊月初八")]),
    ("把这个bug转给前端的赵一鸣。", [P("赵一鸣")]),
    ("今天中午吃什么好呢？", []),
    ("下个月三号去杭州出差，住三天。", [E("去杭州出差", ["下个月三号", "11月3日"])]),
    ("我们的App叫VoxFlow，别写成Voice Flow。", [T("VoxFlow")]),
    ("后天下午两点在三楼会议室面试候选人。", [E("面试候选人", ["后天下午两点", "10月22日"])]),
    ("记得给小王回电话。", [P("小王")]),
    ("这周末不加班，好好休息。", []),
    ("项目经理换成了孙佳怡。", [P("孙佳怡")]),
    ("公司地址是科技园南路88号。", [F("公司地址是科技园南路88号")]),
]

# (memories, text, expected). Expected equal to the text means nothing should be added.
FILL = [
    (["评审会（10月21日周三下午三点）"], "提醒大家参加评审会。", "提醒大家参加10月21日周三下午三点的评审会。"),
    (["部门例会（每周一早上九点）"], "别忘了明天的部门例会。", "别忘了明天早上九点的部门例会。"),
    (["和欧阳小雨吃饭（周五晚上七点）", "欧阳小雨"], "跟小雨确认一下吃饭的时间。", "跟小雨确认一下周五晚上七点吃饭的时间。"),
    (["公司地址是科技园南路88号"], "快递寄到公司就行。", "快递寄到公司（科技园南路88号）就行。"),
    (["高铁去上海（10月21日早上八点）", "G102"], "明天坐高铁去上海。", "明天早上八点坐G102高铁去上海。"),
    (["交年度报告（10月28日之前）"], "年度报告记得交给财务部。", "年度报告记得在10月28日之前交给财务部。"),
    (["面试候选人（10月22日下午两点，三楼会议室）"], "通知候选人来面试。", "通知候选人10月22日下午两点到三楼会议室面试。"),
    (["去杭州出差（11月3日，住三天）"], "帮我订去杭州的酒店。", "帮我订11月3日去杭州的酒店，住三天。"),
    (["北极星项目上线（下周一）"], "北极星项目上线前要做完测试。", "北极星项目下周一上线前要做完测试。"),
    (["Meeting with Sarah Chen (Thursday at 2pm)"], "Remind me about the meeting with Sarah.",
     "Remind me about the meeting with Sarah Chen on Thursday at 2pm."),
    (["Grant application deadline (November 3rd)"], "Finish the grant application before the deadline.",
     "Finish the grant application before the deadline on November 3rd."),
    (["给牙医打电话改预约（今天下午四点）"], "记得给牙医打电话。", "记得今天下午四点给牙医打电话。"),
    # Nothing to fill: unrelated memories, the text already says it, or it disagrees with memory.
    (["评审会（10月21日周三下午三点）"], "明天交房租。", "明天交房租。"),
    (["部门例会（每周一早上九点）"], "部门例会改到十点了。", "部门例会改到十点了。"),
    (["评审会（10月21日周三下午三点）"], "评审会周三下午三点开，别迟到。", "评审会周三下午三点开，别迟到。"),
    (["王书涵"], "今天的晚霞真好看。", "今天的晚霞真好看。"),
    (["和欧阳小雨吃饭（周五晚上七点）"], "吃饭改到周六了，跟小雨说一声。", "吃饭改到周六了，跟小雨说一声。"),
    (["对芒果过敏"], "帮我点一份水果沙拉。", "帮我点一份水果沙拉。"),
    (["Atlas"], "Deploy it to staging tonight.", "Deploy it to staging tonight."),
    (["交年度报告（10月28日之前）"], "好的，收到。", "好的，收到。"),
]

# (texts, memories, phrases a good summary mentions)
SUMMARY = [
    (["周三下午三点开评审会，记得带电脑。", "王书涵明天上午十点来面试，你接待一下。", "好的，收到。",
      "帮我把会议纪要发群里。"],
     ["评审会（周三下午三点）", "王书涵"], ["评审会", "三点", "王书涵", "面试", "会议纪要"]),
    (["10月28日之前把年度报告交给财务部。", "我对芒果过敏，聚餐别点芒果。", "周五晚上七点和欧阳小雨在海底捞吃饭。"],
     ["交年度报告（10月28日）", "对芒果过敏", "欧阳小雨"], ["年度报告", "10月28日", "欧阳小雨", "周五"]),
    (["Meeting with Sarah Chen on Thursday at 2pm about the Q4 budget.", "Please review the pull request.",
      "Our staging server is called Atlas."],
     ["Meeting with Sarah Chen (Thursday at 2pm)", "Atlas"], ["Sarah", "Thursday", "budget", "pull request"]),
    (["明天早上八点的高铁去上海，G102次。", "帮我订上海的酒店，住两晚。", "下个月三号去杭州出差。"],
     ["高铁去上海（明天早上八点）", "去杭州出差（11月3日）"], ["上海", "八点", "酒店", "杭州"]),
    (["今天下午四点给牙医打电话改预约。", "房租每个月十五号交。", "嗯嗯，好的。", "记得给小王回电话。"],
     ["给牙医打电话（今天下午四点）", "小王"], ["牙医", "房租", "小王"]),
]


def main() -> None:
    def write(name, rows):
        with (HERE / name).open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    write("extract.jsonl", [{"id": f"ext-{i:03d}", "today": TODAY, "text": text, "expected": expected}
                            for i, (text, expected) in enumerate(EXTRACT, 1)])
    write("fill.jsonl", [{"id": f"fill-{i:03d}", "memories": memories, "text": text, "expected": expected}
                         for i, (memories, text, expected) in enumerate(FILL, 1)])
    write("summary.jsonl", [{"id": f"sum-{i:03d}", "day": TODAY, "texts": texts, "memories": memories,
                             "mentions": mentions} for i, (texts, memories, mentions) in enumerate(SUMMARY, 1)])
    print(len(EXTRACT), len(FILL), len(SUMMARY))


if __name__ == "__main__":
    main()
