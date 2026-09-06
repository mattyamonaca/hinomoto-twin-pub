# Hinomoto Twin Pub

公開統計に基づいて、市区町村別のペルソナ属性分布を生成するプロジェクトです。

**v2では「市区町村 × 年齢 × 性別 × 最終学歴 × 個人就業年収」を収録しています。** 最終学歴は国勢調査の学校区分に基づき、在学中・未就学・不詳を別区分にしています。

更新：2026年9月6日。人口・地域境界・学歴は2020年、所得は2022年、税務補助は2022年度の統計を使用しています。2026年の現況推計ではありません。

**公開ページ（GitHub Pages）：https://mattyamonaca.github.io/hinomoto-twin-pub/**

都道府県 → 市区町村 → 年齢 → 性別 → 学歴 → 年収帯のノードを展開し、各項目の値がどの統計からどう導出されたかをステップ形式で確認できます。推定方法の詳細は [logic.html](https://mattyamonaca.github.io/hinomoto-twin-pub/logic.html) にまとめています。

## 提供する分布

主出力は **P（年齢, 性別, 学歴, 年収｜市区町村）**。市区町村を選ぶと、13年齢 × 2性別 × 8学歴 × 16年収の確率が合計1になります。

- 1,741市区町村と175政令市行政区、計1,916地域・6,376,448セル。
- 15歳以上の住民を対象とし、外国人住民・非就業者を含みます。
- 性別は公表統計の「男・女」です。性自認を推定する属性ではありません。
- 年収は主な仕事から通常得る年額。給与は税込み、事業は経費控除後。副業・年金・資産収入は含みません。
- 2020年人口が0の双葉町は確率が未定義です。人口のある1,915地域で分布を提供します。
- 性別・学歴を集約すると従来の市区町村別年齢・年収分布を再現します。

主なファイルは以下のとおりです。`data/`・`validation/` は設定したデータルート内の相対パスです。コードリポジトリとは別に保存します。

| パス | 内容 |
|---|---|
| `data/municipality_age_sex_education_income.csv.gz` | 全国の5属性分布。UTF-8・gzip圧縮CSV |
| `data/municipalities_v2/{市区町村コード}.json.gz` | 地域ごとの分布。例えば港区は13103 |
| `data/municipality_model_v2.npz` | Pythonで読み込む推定人数の配列 |
| `data/schema_v2.json` | 行列の軸、区分コード・名称、確率の定義 |
| `data/education_bins.csv`, `data/sex_bins.csv` | 追加属性の区分と注意点 |
| `data/geography.csv`, `data/age_bins.csv`, `data/income_bins.csv` | 地域・年齢・年収の定義 |
| `data/examples_v2.csv` | 5都市での性別・学歴を指定した推定例 |
| `validation/education_verification.json` | 5属性版の検証結果 |
| `validation/education_sensitivity.json` | 学歴×所得の移植仮定・平滑化・不詳の扱いに対する感度分析 |
| `site/index.html` | 公開ページ（[GitHub Pages](https://mattyamonaca.github.io/hinomoto-twin-pub/)）。導出ステップ・参照データ・検証の範囲を表示 |

CSVのコード列は文字列で読み込んでください。政令市は市全体と各区を含むため、全国集計では両方を同時に合計しないでください。`geography_level=municipality` の1,741地域を使うと重複を避けられます。

CSVの `p_age_sex_education_income_given_municipality` が主出力、`p_income_given_municipality_age_sex_education` は年齢・性別・学歴をすべて条件にした年収確率です。`estimated_count` は小数を含む期待人数です。人口0の条件付き分布はCSVで空欄、JSONでnullです。

## 最終学歴の8区分

| コード | 区分 | 注意点 |
|---|---|---|
| E01 | 小学校・中学校 | 所得表に合わせて統合 |
| E02 | 高校・旧中相当 | 所得接続では専門学校2年未満も含める近似 |
| E03 | 短大・高専等 | 一定の専門学校2年以上4年未満等を含む |
| E04 | 大学等 | 一定の専門学校4年以上等を含む。学士号保有の意味ではない |
| E05 | 大学院 | 修士・専門職・博士を統合 |
| E06 | 在学中 | 卒業済みの学校種別は推定しない |
| E07 | 未就学 | 学校に在学したことがない者 |
| E08 | 不詳 | 卒業学校不詳と在学状況不詳 |

専門学校の扱いは両統計の定義を近づけるための対応付けです。卒業時期や入学資格による厳密な対応を再現できない部分は仮定として記録しています。詳しくは [学歴追加の推定方法](METHOD_V2.md) を参照してください。

今回のモデルでは、不詳が約13.98%、在学中が約6.88%です。不詳を所得から推測して既知の学歴に割り振る処理はしていません。

## 条件付き分布とペルソナ抽出

Python 3.11以上で実行します。コードとデータを別々に取得します。既存の計算済みデータがあれば再計算は不要です。初回の配置方法は [データの管理](DATA.md) を参照してください。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# データルートを指定（省略時はコードの隣の hinomoto-twin-data）
export HINOMOTO_DATA_ROOT="../hinomoto-twin-data"
# 初回のみ：固定版の入力データを取得して計算
make dataset
make build

# 港区の全4軸の同時分布（市区町村は条件）
python src/persona_v2.py --municipality 13103

# 港区・35～39歳・男性・大学等の年収分布
python src/persona_v2.py --municipality 13103 --age 35 --sex male --education E04 --income-only

# 同じ条件から10人を抽出
python src/persona_v2.py --municipality 13103 --age 35 --sex male --education E04 --sample 10 --seed 7

# 性別と学歴は分布から抽出
python src/persona_v2.py --municipality 13103 --age 35 --sample 10 --seed 7
```

`--age 35` は35～39歳区分を指定します。1歳単位や1円単位の数値は生成しません。性別は `1/male/男` または `2/female/女`、学歴はE01～E08で指定できます。任意の条件だけを指定し、残りは分布から抽出できます。

Pythonからは `src/persona_v2.py` の `PersonaDistributionV2` を読み込みます。`distribution()` は年齢・性別・学歴・年収の4軸を維持し、指定された属性の軸の長さを1にします。`income_distribution()` は残りの属性を集約した16年収確率を返します。出力はすべて、指定した条件の下で合計1になります。

## 推定と検証

性別はv1で使っていた内部の人口・所得配列を出力に残しています。学歴は2020国勢調査11-2の市区町村別年齢・性別・学校区分人口を基準にします。学歴と就業の関連を国勢調査12-1、学歴と年収の関連を2022就業構造基本調査04000から取り出し、地域の人口と従来の所得分布の双方に合うよう調整します。

**学歴と所得を独立に掛け合わせてはいません。** 一方、全国の学歴別所得の関連を地域に移植する仮定があり、実測された市区町村別学歴・所得の同時分布ではありません。内部整合性の検証と、小地域での精度保証は区別してください。

[推定方法・制約・限界（v2）](METHOD_V2.md)／[基礎モデル（v1）](METHOD.md)／[全出典](SOURCES.md)

### 検証の範囲と感度分析

| 項目 | 内容 |
|---|---|
| 検証できた範囲 | 86都市 × 年齢13区分の就業者の所得構成（TV 0.09328、税係数の都道府県単位交差検証） |
| 未検証の範囲 | 町村・行政区、性別別、学歴別の所得構成、非就業者を含む住民全体の分布 |
| 集計表示の意味 | 公開ページの都道府県・全国は市区町村モデルの加重集計。公表値と一致するのは都道府県 × 性別 × 年齢 × 所得既知の有業者の構成比のみで、年齢・性別をまとめた集計は公表表の総数行と一致しない |
| 感度分析 | `python src/sensitivity_education.py` → `validation/education_sensitivity.json`。有業所得の初期形状にある学歴差を半分に弱めると学歴別の500万円以上の割合は平均1.9ポイント、初期形状の学歴差を除く（学歴別就業率は維持）と4.2ポイント、就業率の学歴差も除くと4.5ポイント動く。平滑化・所得不詳・学歴不詳の扱いに対する感度は0.1〜0.4ポイント |
| 学歴不詳 | 独立区分として保持。不詳率は地域・年齢・性別で大きく異なり（全国13.98%、港区35～39歳男性50.14%）、公開ページで選択中の条件の不詳率を表示 |

詳細は [METHOD_V2.md](METHOD_V2.md) の「学歴不詳の扱いと補完モードの仕様」「移植仮定の感度分析」「検証の範囲」を参照してください。

**モデル改善の比較実験（Issue #12）**：学歴構成で地域の所得分布を再推定する M1 は、86都市の out-of-fold 比較で加重TVを 0.09328 → 0.09000（3.5%）改善し、仮想人口実験では税務指標が弱い条件で一貫して改善しました。本番の既定値は M0 のままで、設計・データ契約・評価設定・結果・採否理由は [docs/EXPERIMENT_M12.md](docs/EXPERIMENT_M12.md) にまとめています（`make experiment`、`make synthetic` で再現）。

## 元データと再実行

| 場所 | 内容 | コード側のGit管理 |
|---|---|---|
| `src/` | 取得・加工・推定・出力・検証・抽出 | 対象 |
| `catalog/` | 出典・固定版ハッシュ・取得用表定義・入力形式 | 対象 |
| `site/` | 分布を埋め込まない画面コード | 対象 |
| `$HINOMOTO_DATA_ROOT/raw/` | 元Excel・所得表レスポンス | 対象外 |
| `$HINOMOTO_DATA_ROOT/sources/` | 正規化済み入力 | 対象外 |
| `$HINOMOTO_DATA_ROOT/data/` | 全分布・計算用配列・推定例 | 対象外 |
| `$HINOMOTO_DATA_ROOT/validation/` | 検証結果・処理品質 | 対象外 |
| `$HINOMOTO_DATA_ROOT/web/` | 公開ページ用データ | 対象外 |

`make dataset` で固定版の正規化済み入力を別途取得できます。取得後の推定はオフラインで実行できます。`make paths` で実際の参照先を確認してください。入力と出力の置き場所は個別にも変更できます。移行、アーカイブ、設定の詳細は [DATA.md](DATA.md) を参照してください。

```sh
make build          # v1の基礎推定 → v2の性別・学歴追加
make verify         # v1・v2を検証
make sample
```

v1の計算済みデータがある場合、追加分だけは `make build-education`、検証は `make verify-education` で実行できます。makeがない場合は対応するPythonプログラムを順に実行してください。

```sh
python src/build_education.py
python src/export_education.py
python src/verify_education.py
```

元データからやり直す場合は `make install-source` の後、`make fetch` で取得・加工、保存済み原表なら `make prepare` で加工できます。学歴分だけなら `python src/fetch_education.py` と `python src/parse_education.py` です。e-Statの画面構造・原表更新に影響される可能性があるため、再取得時は出典と検証結果も確認してください。

## 互換性と開発

従来のCSV・NPZ・地域別JSONと `src/persona.py` はv1の形式で利用できます。v1の説明書は [README_V1.md](README_V1.md) に残しています。v2の生成結果には `_v2` または `sex_education` を含む名前を付けています。

開発方針：[CONTRIBUTING.md](CONTRIBUTING.md)。ソフトウェアライセンスは所有者による選定前です：[LICENSE_STATUS.md](LICENSE_STATUS.md)。
