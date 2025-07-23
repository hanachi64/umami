import streamlit as st
import pandas as pd
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
ticket_types = st.sidebar.multiselect("馬券種を選択してください", ["単勝", "複勝"], default=["単勝"])

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

    # オッズカラム判定
    odds_candidates = ["オッズ", "単勝", "単勝オッズ"]
    odds_col = next((col for col in odds_candidates if col in race_df.columns), None)
    if odds_col is None:
        st.error("⚠️ 出走表に『オッズ』または『単勝』というカラムが見つかりません。")
        st.stop()

    # 単勝オッズを統一カラムにコピー
    race_df["単勝オッズ"] = race_df[odds_col]

    # マッピング準備
    df = race_df.copy()
    rate_map = rate_df.set_index("馬名")["複勝率"].to_dict()

    # スコア計算
    df["人気スコア"] = 1 / df["単勝オッズ"]
    df["複勝率スコア"] = df["馬名"].map(rate_map).fillna(0.0)

    # 補正入力（±0.05刻み）
    st.subheader("③ 各馬の補正項目（±0.05刻み）")
    correction_fields = {
        "距離適性": 0.10,
        "脚質適性": 0.10,
        "馬場適性": 0.05,
        "枠順適性": 0.05
    }
    for field, max_val in correction_fields.items():
        df[field + "補正"] = df["馬名"].apply(
            lambda name: st.selectbox(
                f"{name} の {field}",
                options=[round(x, 2) for x in [-max_val, -max_val/2, 0.0, max_val/2, max_val]],
                index=2,
                key=f"{name}_{field}"
            )
        )
    df["補正スコア"] = df[[f + "補正" for f in correction_fields]].sum(axis=1).astype(float)

    # 総合スコアと確率
    df["総合スコア"] = df["人気スコア"] * 0.5 + df["複勝率スコア"] * 0.3 + df["補正スコア"] * 0.2
    df["確率"] = normalize(df["総合スコア"])

    # 期待値計算
    if "単勝" in ticket_types:
        df["単勝期待値"] = df["単勝オッズ"] * df["確率"]
    if "複勝" in ticket_types and "複勝オッズ" in df.columns:
        df["複勝期待値"] = df["複勝オッズ"] * df["確率"]

    # 結果表示
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

    # 払戻シミュレーター
    st.subheader("⑤ 払戻しシミュレーター")
    bet = st.number_input("1点あたりの購入額（円）", min_value=100, step=100, value=100)
    for t in ticket_types:
        col = f"{t}期待値"
        if col in df.columns:
            df[f"{t}払戻期待値"] = df[col] * bet
            st.markdown(f"### {t} 予想払戻額（1点 {bet}円）")
            st.dataframe(df[["馬名", col, f"{t}払戻期待値"]])
else:
    st.info("出走表と複勝率CSVを両方アップロードしてください。")

