import streamlit as st
import pandas as pd
import itertools
from chardet.universaldetector import UniversalDetector

# --- エンコーディング自動検出 ---
def detect_encoding(file_obj):
    detector = UniversalDetector()
    file_obj.seek(0)
    for line in file_obj:
        detector.feed(line)
        if detector.done:
            break
    detector.close()
    file_obj.seek(0)
    return detector.result['encoding']

# --- 安全なCSV読み込み ---
def safe_read_csv(file_obj):
    encoding = detect_encoding(file_obj)
    try:
        return pd.read_csv(file_obj, encoding=encoding)
    except Exception:
        file_obj.seek(0)
        return pd.read_csv(file_obj, encoding=encoding, sep="\t")

# --- 正規化ユーティリティ ---
def normalize(series):
    total = series.sum()
    return series / total if total > 0 else series

# --- Streamlit UI ---
st.title("競馬馬券 期待値比較アプリ")
st.sidebar.header("設定")

# 馬券種の選択
ticket_types = st.sidebar.multiselect("馬券種を選択してください", ["単勝", "複勝", "馬連", "ワイド"], default=["単勝"])

# 期待値の閾値
threshold = st.sidebar.number_input("期待値の閾値（例：1.2）", min_value=0.0, value=1.0, step=0.05)

# 出走表のアップロード
st.subheader("① 出走表CSVアップロード")
st.markdown("⚠️ **このファイルには『馬名』『オッズ（単勝）』のカラムが必要です。**")
race_file = st.file_uploader("出走表CSVをアップロード", type=["csv"])

# 複勝率CSVのアップロード
st.subheader("② 合成複勝率CSVアップロード（別アプリ出力）")
rate_file = st.file_uploader("複勝率CSVをアップロード", type=["csv"])
st.markdown("⚠️ **血統アプリから出力したCSVは、1行目などにある条件行を削除してからアップロードしてください。**")

if race_file and rate_file:
    try:
        race_df = safe_read_csv(race_file)
        rate_df = safe_read_csv(rate_file)
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました：{e}")
        st.stop()

    # 単勝オッズ列の特定と変換
    odds_candidates = ["オッズ", "単勝", "単勝オッズ"]
    odds_col = next((col for col in odds_candidates if col in race_df.columns), None)
    if odds_col is None:
        st.error("⚠️ 出走表に『オッズ』または『単勝』というカラムが見つかりません。")
        st.stop()
    race_df["単勝オッズ"] = pd.to_numeric(race_df[odds_col], errors="coerce")

    df = race_df.copy()
    rate_map = rate_df.set_index("馬名")["複勝率"].to_dict()

    df["人気スコア"] = 1 / df["単勝オッズ"]
    df["複勝率スコア"] = df["馬名"].map(rate_map)
    df["複勝率スコア"] = pd.to_numeric(df["複勝率スコア"], errors="coerce").fillna(0.0)

    # 補正項目表形式UI
    st.subheader("③ 各馬の補正項目（横並び・±0.05刻み）")
    correction_fields = {
        "距離適性": 0.10,
        "脚質適性": 0.10,
        "馬場適性": 0.05,
        "枠順適性": 0.05
    }

    corrections = {f + "補正": [] for f in correction_fields}
    st.markdown("### 補正入力表")
    header = st.columns([1] + [1 for _ in correction_fields])
    header[0].markdown("**馬名**")
    for i, f in enumerate(correction_fields):
        header[i+1].markdown(f"**{f}**")

    for idx, row in df.iterrows():
        cols = st.columns([1] + [1 for _ in correction_fields])
        cols[0].markdown(row["馬名"])
        for i, (field, max_val) in enumerate(correction_fields.items()):
            val = cols[i+1].selectbox(
                "",
                options=[round(x, 2) for x in [-max_val, -max_val/2, 0.0, max_val/2, max_val]],
                index=2,
                key=f"{row['馬名']}_{field}"
            )
            corrections[field + "補正"].append(val)

    for key, values in corrections.items():
        df[key] = pd.to_numeric(values, errors='coerce')

    df["補正スコア"] = df[[f + "補正" for f in correction_fields]].sum(axis=1)
    df["総合スコア"] = df["人気スコア"] * 0.5 + df["複勝率スコア"] * 0.3 + df["補正スコア"] * 0.2
    df["確率"] = normalize(df["総合スコア"])

    # 期待値計算
    if "単勝" in ticket_types:
        df["単勝期待値"] = df["単勝オッズ"] * df["確率"]
    if "複勝" in ticket_types and "複勝オッズ" in df.columns:
        df["複勝期待値"] = df["複勝オッズ"] * df["確率"]

    # 期待値表示
    st.subheader("④ 期待値表示（黄色 = 閾値以上）")
    for t in ticket_types:
        col = f"{t}期待値"
        if col in df.columns:
            styled_df = df[["馬名", "単勝オッズ", "確率", col]].style.applymap(
                lambda v: "background-color: yellow" if isinstance(v, (int, float)) and v >= threshold else "",
                subset=[col]
            )
            st.markdown(f"### {t} 期待値")
            st.dataframe(styled_df)

    # 払戻しシミュレーター
    st.subheader("⑤ 払戻しシミュレーター")
    bet = st.number_input("1点あたりの購入額（円）", min_value=100, step=100, value=100)
    for t in ticket_types:
        col = f"{t}期待値"
        if col in df.columns:
            df[f"{t}払戻期待値"] = df[col] * bet
            st.markdown(f"### {t} 予想払戻額（1点 {bet}円）")
            st.dataframe(df[["馬名", col, f"{t}払戻期待値"]])

    # オッズ手入力フォーム（任意）
    st.subheader("⑥ 手入力オッズ（単勝・複勝 + 期待値表示）")
    st.markdown("⚠️ 出走表CSVにオッズが無い場合はここで手入力してください")
    for idx, row in df.iterrows():
        cols = st.columns([2, 1, 1, 1, 1])
        cols[0].markdown(f"**{row['馬名']}**")

        tan_input = cols[1].number_input(f"単勝_{row['馬名']}", value=float(row.get("単勝オッズ", 0.0)), step=0.1, key=f"tan_input_{idx}")
        fuku_input = cols[2].number_input(f"複勝_{row['馬名']}", value=float(row.get("複勝オッズ", 0.0)), step=0.1, key=f"fuku_input_{idx}")

        df.at[idx, "単勝オッズ"] = tan_input
        df.at[idx, "複勝オッズ"] = fuku_input

        t_exp = tan_input * row["確率"] if tan_input > 0 else 0
        f_exp = fuku_input * row["確率"] if fuku_input > 0 else 0

        cols[3].markdown(f"🟡 単勝期待値: {t_exp:.2f}")
        cols[4].markdown(f"🟢 複勝期待値: {f_exp:.2f}")

# 馬連・ワイド用の手入力UI
if "馬連" in ticket_types or "ワイド" in ticket_types:
    st.subheader("⑦ 馬連・ワイド 手入力 + 期待値")
    horses = df["馬名"].tolist()
    pairs = list(itertools.combinations(horses, 2))

    for i, (h1, h2) in enumerate(pairs):
        cols = st.columns([2, 1, 1, 1, 1])
        cols[0].markdown(f"**{h1} × {h2}**")

        umaren_odds = cols[1].number_input(f"馬連_{h1}_{h2}", min_value=0.0, step=0.1, key=f"umaren_{i}")
        wide_odds = cols[2].number_input(f"ワイド_{h1}_{h2}", min_value=0.0, step=0.1, key=f"wide_{i}")

        # 安全に確率取得（該当がなければ0.0に）
        prob1 = df[df["馬名"] == h1]["確率"]
        prob1 = prob1.values[0] if not prob1.empty else 0.0

        prob2 = df[df["馬名"] == h2]["確率"]
        prob2 = prob2.values[0] if not prob2.empty else 0.0

        pair_prob = prob1 * prob2 * 2  # 簡易合成確率（独立仮定 ×2補正）

        uma_exp = umaren_odds * pair_prob if umaren_odds > 0 else 0
        wide_exp = wide_odds * pair_prob if wide_odds > 0 else 0

        cols[3].markdown(f"🟣 馬連期待値: {uma_exp:.2f}")
        cols[4].markdown(f"🔵 ワイド期待値: {wide_exp:.2f}")


else:
    st.info("出走表と複勝率CSVを両方アップロードしてください。")
