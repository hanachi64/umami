import streamlit as st
import pandas as pd

# --- ユーティリティ関数 ---
def normalize(series):
    total = series.sum()
    return series / total if total > 0 else series

# --- Streamlit UI ---
st.title("競馬馬券 期待値比較アプリ")

st.sidebar.header("設定")

# 馬券種の選択
ticket_types = st.sidebar.multiselect(
    "馬券種を選択してください",
    ["単勝", "複勝"],
    default=["単勝"]
)

# 期待値の閾値
threshold = st.sidebar.number_input("期待値の閾値（例：1.2）", min_value=0.0, value=1.0, step=0.05)

# 出走表CSVアップロード
st.subheader("出走表CSVアップロード")
race_file = st.file_uploader("出走表CSVをアップロード", type=["csv"])

# 種牡馬・母父馬の複勝率CSVアップロード
st.subheader("合成複勝率CSVアップロード（別アプリ出力）")
rate_file = st.file_uploader("複勝率CSVをアップロード", type=["csv"])

if race_file and rate_file:
    race_df = pd.read_csv(race_file)
    odds_df = pd.read_csv(rate_file)
    rate_map = odds_df.set_index("馬名")["複勝率"].to_dict()
    
    st.write("出走表データ", race_df)
    st.write("合成複勝率データ", odds_df)

    df = race_df.copy()
    df["人気スコア"] = 1 / df["単勝オッズ"]
    df["複勝率スコア"] = df["馬名"].map(rate_map).fillna(0.0)

    # 補正セレクトボックス
    correction_fields = ["距離適性", "脚質適性", "馬場適性"]
    corrections = {}
    for field in correction_fields:
        st.subheader(f"{field}補正")
        corrections[field] = []
        for i, row in df.iterrows():
            val = st.selectbox(
                f"{row['馬名']} の {field}",
                options=[-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15],
                index=3,
                key=f"{row['馬名']}_{field}"
            )
            corrections[field].append(val)
    for field in correction_fields:
        df[field + "補正"] = corrections[field]
    df["補正スコア"] = df[[f + "補正" for f in correction_fields]].sum(axis=1)

    # 総合スコアと確率
    df["総合スコア"] = (
        df["人気スコア"] * 0.5 +
        df["複勝率スコア"] * 0.3 +
        df["補正スコア"] * 0.2
    )
    df["確率"] = normalize(df["総合スコア"])

    # 期待値計算
    if "単勝" in ticket_types:
        df["単勝期待値"] = df["単勝オッズ"] * df["確率"]
    if "複勝" in ticket_types and "複勝オッズ" in df.columns:
        df["複勝期待値"] = df["複勝オッズ"] * df["確率"]

    # 結果表示
    st.subheader("期待値表示")
    for t in ticket_types:
        col = f"{t}期待値"
        if col in df.columns:
            styled_df = df[["馬名", "単勝オッズ", "確率", col]].style.applymap(
                lambda v: "background-color: yellow" if isinstance(v, (int, float)) and v >= threshold else ""
            , subset=[col])
            st.markdown(f"### {t} 期待値")
            st.dataframe(styled_df)

    # 払戻計算
    st.subheader("払戻計算機")
    bet = st.number_input("1点あたりの購入額（円）", min_value=100, step=100, value=100)
    for t in ticket_types:
        col = f"{t}期待値"
        if col in df.columns:
            df[f"{t}払戻期待値"] = df[col] * bet
            st.markdown(f"### {t} 予想払戻額（1点あたり {bet}円）")
            st.dataframe(df[["馬名", col, f"{t}払戻期待値"]])
else:
    st.info("出走表と複勝率CSVを両方アップロードしてください。")
