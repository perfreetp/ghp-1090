"""生成测试数据 - 用于验证工具功能"""

import os
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np


def generate_transactions(n: int = 10000, seed: int = 42) -> pd.DataFrame:
    """生成模拟交易数据"""
    np.random.seed(seed)
    random.seed(seed)

    # 基础实体池
    n_cards = n // 10
    n_merchants = n // 50
    n_devices = n // 8

    card_ids = [f"622202{random.randint(1000000000, 9999999999)}" for _ in range(n_cards)]
    merchant_ids = [f"M{random.randint(100000, 999999)}" for _ in range(n_merchants)]
    merchant_names = [
        "京东商城", "天猫超市", "拼多多", "美团外卖", "饿了么",
        "携程旅行", "去哪儿", "滴滴出行", "支付宝", "微信支付",
        "中国石油", "中国石化", "星巴克", "麦当劳", "肯德基",
        "优衣库", "海澜之家", "屈臣氏", "华润万家", "沃尔玛",
    ]
    mcc_codes = ["5411", "5812", "5814", "5541", "4111", "5999", "5311", "5691", "5211", "4511"]
    provinces = ["北京市", "上海市", "广东省", "浙江省", "江苏省",
                 "四川省", "湖北省", "山东省", "河南省", "福建省"]
    cities = ["北京", "上海", "深圳", "广州", "杭州", "南京", "成都", "武汉", "青岛", "郑州"]
    channels = ["POS", "ECOM", "MOBILE", "QR", "APP"]
    txn_types = ["消费", "取现", "转账", "预授权"]
    currencies = ["CNY"] * 95 + ["USD", "HKD"] * 2 + ["EUR"]

    # 生成欺诈模式的卡号
    fraud_cards = random.sample(card_ids, max(10, n_cards // 20))
    fraud_merchants = random.sample(merchant_ids, max(5, n_merchants // 10))

    base_time = datetime(2024, 6, 1)
    rows = []

    for i in range(n):
        is_fraud = False
        is_suspicious = False

        card = random.choice(card_ids)
        merchant = random.choice(merchant_ids)
        province = random.choice(provinces)
        city = random.choice(cities)
        channel = random.choice(channels)
        txn_type = random.choices(txn_types, weights=[85, 5, 5, 5])[0]
        currency = random.choice(currencies)

        # 时间：按 5 个月随机分布
        offset = random.randint(0, 150) * 86400 + random.randint(0, 86399)
        txn_time = (base_time + timedelta(seconds=offset)).strftime("%Y-%m-%d %H:%M:%S")

        # 基础金额
        amount = round(random.lognormvariate(5.5, 1.2), 2)

        # 注入欺诈模式
        if card in fraud_cards:
            if random.random() < 0.35:
                is_fraud = True
                amount = round(amount * random.uniform(2, 10), 2)
                if random.random() < 0.5:
                    province = random.choice(provinces)
                    city = random.choice([c for c in cities if c[:2] != province[:2]])
        if merchant in fraud_merchants:
            if random.random() < 0.2:
                is_suspicious = True

        # 规则命中
        rule_hit = np.nan
        if is_fraud or (random.random() < 0.02):
            rules = []
            if amount > 10000:
                rules.append("R001")
            if province != cities[cities.index(city) % len(provinces)] if city in cities else False:
                if random.random() < 0.7:
                    rules.append("R002")
            if is_fraud:
                rules.append("R003")
            if not rules:
                rules = ["R004"]
            rule_hit = ",".join(rules)

        # 人工结论
        manual_result = np.nan
        if is_fraud and random.random() < 0.6:
            manual_result = "确认欺诈"
        elif is_suspicious and random.random() < 0.4:
            manual_result = "可疑待确认"
        elif random.random() < 0.01:
            manual_result = "真实交易"

        # 风险评分
        risk_score = random.randint(0, 30)
        if is_suspicious:
            risk_score = random.randint(40, 70)
        if is_fraud:
            risk_score = random.randint(75, 99)

        rows.append({
            "txn_id": f"T{20240601 + i:012d}",
            "card_no": card,
            "cardholder_name": f"{random.choice('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜')}"
                              f"{random.choice('伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英文华建国建军春燕玲鹏飞')}"
                              f"{random.choice('华平国林民东辉龙飞鹏博浩凯健俊超阳勇兵海亮杰峰泽晨')}",
            "id_card": f"{random.randint(110000, 659000)}"
                       f"{random.randint(1960, 2005)}"
                       f"{random.randint(101, 1231):04d}"
                       f"{random.randint(1000, 9999)}",
            "phone": f"1{random.choice(['3','5','7','8','9'])}{random.randint(100000000, 999999999)}",
            "txn_time": txn_time,
            "txn_amount": f"{amount:.2f}" if random.random() > 0.1 else f"¥{amount:.2f}",
            "currency": currency,
            "merchant_id": merchant,
            "merchant_name": random.choice(merchant_names),
            "mcc": random.choice(mcc_codes),
            "txn_type": txn_type,
            "channel": channel,
            "country": "中国",
            "province": province,
            "city": city,
            "device_id": f"DEV{random.randint(1, n_devices):08d}",
            "ip": f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,255)}",
            "pos_entry_mode": random.choice(["CHIP", "MAG", "CONTACTLESS", "MANUAL", "ECOM"]),
            "installment": random.choices([np.nan, 3, 6, 12, 24], weights=[70, 10, 10, 7, 3])[0],
            "cashback": round(amount * random.uniform(0, 0.05), 2) if random.random() < 0.3 else np.nan,
            "risk_score": risk_score,
            "rule_hit": rule_hit,
            "manual_review": "是" if manual_result is not np.nan else "否",
            "manual_result": manual_result,
            "auth_code": f"{random.randint(100000, 999999)}",
            "issuer_bank": random.choice(["工商银行", "建设银行", "农业银行", "中国银行",
                                           "招商银行", "交通银行", "浦发银行", "中信银行"]),
            "acquirer_bank": random.choice(["收单行A", "收单行B", "收单行C", "银联"]),
            "terminal_id": f"TERM{random.randint(100000, 999999)}",
        })

    df = pd.DataFrame(rows)
    # 注入一些重复
    dup_idx = random.sample(range(len(df)), n // 100)
    dup_rows = df.iloc[dup_idx].copy()
    df = pd.concat([df, dup_rows], ignore_index=True)

    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def generate_chargebacks(txn_df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """生成拒付数据"""
    np.random.seed(seed)
    random.seed(seed)

    # 人工标记的欺诈 + 高风险评分更易产生拒付
    fraud_mask = (txn_df["manual_result"] == "确认欺诈") | (txn_df["risk_score"] > 85)
    candidates = txn_df[fraud_mask].index.tolist()

    # 再挑一些随机的
    extra = random.sample(range(len(txn_df)), len(candidates) // 5)
    candidates = list(set(candidates + extra))

    rows = []
    for idx in candidates:
        row = txn_df.iloc[idx]
        txn_dt = datetime.strptime(row["txn_time"], "%Y-%m-%d %H:%M:%S")
        cb_time = (txn_dt + timedelta(days=random.randint(7, 60))).strftime("%Y-%m-%d %H:%M:%S")

        # 拒付结果
        is_actual_fraud = row["manual_result"] == "确认欺诈" or row["risk_score"] > 85
        if is_actual_fraud and random.random() < 0.8:
            result = "商户败诉"
        elif random.random() < 0.4:
            result = "商户败诉"
        else:
            result = "商户胜诉"

        rows.append({
            "txn_id": row["txn_id"],
            "chargeback_time": cb_time,
            "chargeback_reason": random.choice(["4837", "4853", "4863", "4871", "4903"]),
            "chargeback_amount": row["txn_amount"].replace("¥", "").replace(",", ""),
            "chargeback_result": result,
        })

    return pd.DataFrame(rows)


def generate_blacklist(seed: int = 42) -> pd.DataFrame:
    """生成黑名单数据"""
    np.random.seed(seed)
    random.seed(seed)

    rows = []
    # 黑名单卡号
    for _ in range(30):
        rows.append({
            "entity_type": "card",
            "entity_value": f"622202{random.randint(1000000000, 9999999999)}",
            "list_time": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 150))).strftime("%Y-%m-%d"),
            "risk_level": random.choice(["高", "中", "高", "极高"]),
            "source": random.choice(["公安数据", "欺诈库", "行内数据", "外部风控"]),
        })
    # 黑名单商户
    for _ in range(15):
        rows.append({
            "entity_type": "merchant",
            "entity_value": f"M{random.randint(100000, 999999)}",
            "list_time": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 150))).strftime("%Y-%m-%d"),
            "risk_level": random.choice(["高", "中", "高"]),
            "source": random.choice(["行内数据", "欺诈库"]),
        })
    # 黑名单设备
    for _ in range(20):
        rows.append({
            "entity_type": "device",
            "entity_value": f"DEV{random.randint(1, 99999999):08d}",
            "list_time": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 150))).strftime("%Y-%m-%d"),
            "risk_level": random.choice(["中", "高"]),
            "source": random.choice(["设备指纹库", "行内数据"]),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="生成欺诈样本测试数据")
    parser.add_argument("-n", "--num", type=int, default=5000, help="交易样本数 (默认: 5000)")
    parser.add_argument("-o", "--output", default="./test_data", help="输出目录")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"生成 {args.num} 条交易数据...")
    txn_df = generate_transactions(args.num, args.seed)
    txn_path = out_dir / "transactions.csv"
    txn_df.to_csv(txn_path, index=False, encoding="utf-8-sig")
    print(f"  已保存: {txn_path} ({len(txn_df)} 行)")

    print("生成拒付数据...")
    cb_df = generate_chargebacks(txn_df, args.seed)
    cb_path = out_dir / "chargebacks.csv"
    cb_df.to_csv(cb_path, index=False, encoding="utf-8-sig")
    print(f"  已保存: {cb_path} ({len(cb_df)} 行)")

    print("生成黑名单数据...")
    bl_df = generate_blacklist(args.seed)
    bl_path = out_dir / "blacklists.csv"
    bl_df.to_csv(bl_path, index=False, encoding="utf-8-sig")
    print(f"  已保存: {bl_path} ({len(bl_df)} 行)")

    print(f"\n✅ 测试数据已生成至: {out_dir}")
    print(f"\n使用示例:")
    print(f"  fraud-org pipeline -t {out_dir / 'transactions.csv'} "
          f"-c {out_dir / 'chargebacks.csv'} -b {out_dir / 'blacklists.csv'} -d ./data_demo")


if __name__ == "__main__":
    main()
