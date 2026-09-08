# 統計の出典と取得記録

[用途別の一覧と参考論文](README.md#利用しているデータベース統計と参考論文) ／ [現在の推定方法](METHOD.md) ／ [データと再現手順](DATA.md)

この文書は原表と取得・加工の記録です。税務指標には過去モデルの入力も含まれます。現在の公開分布は税務補正を使いません。世帯・勤務地・独立評価用税務統計の原表は [世帯](catalog/household/manifest.json)・[勤務地](catalog/workplace/manifest.json)・[税務検証](catalog/tax_status/manifest.json)の取得記録を参照してください。

取得日：2026年9月5日。提供元：総務省統計局・e-Stat。税務指標の原統計は総務省「市町村税課税状況等の調」。これらを本成果物の作成者が加工・推定したもので、政府作成の市区町村別所得推計ではありません。

## 使用ファイル

1. **2020年国勢調査・人口等基本集計、不詳補完結果、参考表1-4**。[Excel原表](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032144437&fileKind=0)。加工後：`census_population_tidy.csv.gz`。国籍総数、年齢15歳以上を抽出し、75歳以上を統合。
2. **2020年国勢調査・就業状態等基本集計、不詳補完結果、参考表1**。[Excel原表](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201519&fileKind=0)。加工後：`census_imputed_age_tidy.csv.gz`。性別・年齢別の人口・就業状態。
3. **同・不詳補完参考表5-1**。[Excel原表](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201523&fileKind=0)。加工後：`census_imputed_detailed_status_tidy.csv.gz`。産業総数の性別・従業上の地位を抽出。
4. **同・表3-1、不詳補完前**。[Excel原表](https://www.e-stat.go.jp/stat-search/file-download?fileKind=0&statInfId=000032201197)。加工後：`census_age_status_tidy.csv.gz`。年齢と従業上の地位の関連の初期値に使用。
5. **2022年就業構造基本調査・地域編02300**。[e-Stat統計表](https://www.e-stat.go.jp/dbview?sid=0004008500)。加工後：`income_tidy.csv.gz`。配偶関係総数、全国・都道府県・都市、所得全階級、年齢全階級を取得。主な仕事からの所得の定義は[公式用語解説](https://www.stat.go.jp/data/shugyou/2022/pdf/yougo.pdf)。
6. **社会・人口統計体系／市区町村のすがた2024／C経済基盤**。[原表](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040186223&fileKind=0)。加工後：`tax_tidy.csv`。C120110課税対象所得（百万円）とC120120納税義務者数（所得割）の2022年度値。[項目説明](https://www.stat.go.jp/data/k-sugata/pdf/setumei.pdf)。2022年度値が原則2021年中の所得に基づく点に注意。

論文は手法の参照として、[Lovelace, Birkin, Ballas & van Leeuwen (2015), Evaluating the Performance of Iterative Proportional Fitting for Spatial Microsimulation](https://www.jasss.org/18/2/21.html), DOI:10.18564/jasss.2768を使用。今回の日本の推定値を実証した論文ではありません。

## 出典データの保存内容

`catalog/manifest.json` に使用した原表のダウンロードURL・ファイルサイズ・SHA-256、加工済み表のSHA-256、所得表の15件の取得レスポンスのSHA-256を保存しました。元Excelとレスポンス本体は、外部データルートの `raw/` に保存します。通常のGit管理からは除外していますが、再取得用プログラムを含めています。計算に必要な加工済み表は外部データルートの `sources/` に配置します。取得は `make dataset`、設定・移行は [DATA.md](DATA.md) を参照してください。

所得表はe-Statの公開閲覧画面が使う読み取り用エンドポイントから取得しました。APIキーを要するe-Stat外部提供APIとは別です。取得時の表定義を `catalog/income_model.json` に保存しています。性別コード0,1,2、地位コード0,1,2,22,23の組合せ15件で、134地域 × 17所得区分 × 14年齢区分を各取得。HTML表からコード・値を読み、総数や男女計を保持した縦持ち表にしました。ダッシュは0として処理し、数値と原表の文字列を保存しています。実装は画面の構造変更に影響されるため、将来の再取得時は確認が必要です。

## 再現する

現在の生成手順は [DATA.md](DATA.md) と [工程仕様](docs/PIPELINE.md) を参照してください。以下は初期の取得・実行記録です。加工済みデータからの推定はオフラインで実行できます。元ファイルから加工し直す場合のみ、ネット接続を用意して実行してください。

```sh
python -m pip install -r requirements-source.txt
python src/download_sources.py
python src/build.py
python src/refine_tax.py
python src/export.py
python src/verify.py
```

`raw/` に元ファイルを取得します。Excel原表のハッシュが取得時と異なる場合は停止するので、更新・訂正を確認してから出典情報も更新してください。所得画面のレスポンスやgzipのメタデータは同じ数値でもバイト列が変わる場合があります。加工後にコード・行数・数値の一致を確認してください。

`economic.xlsx` は取得時の保存名で、内容は旧Excel形式（XLS）です。パーサーはxlrdを使うため拡張子の相違は読み取りに影響しません。

原データを再配布・転用する場合は、各出典の利用条件・出典表示を引き継いでください。推計値を公表する際は「国勢調査・就業構造基本調査・市区町村のすがたを加工したモデル推定」と明記し、基準年と所得定義を併記してください。

## 調査中に取得した未使用データ

`raw/exploratory/` には、原表の選定途中で取得した4ファイルを保存しました。いずれも最終モデルには使っていません。

- `census_employment.xlsx`：2020国勢調査の就業状態表2-2。最終モデルでは不詳補完表を採用。
- `census_status.xlsx`：同・従業上の地位表3-2。最終モデルでは不詳補完表を採用。
- `census_imputed_status.xlsx`：同・就業地位のより粗い不詳補完表。最終モデルでは詳細な5-1を採用。
- `SSDSE-A-2023.csv`：SSDSE-A-2023。今回必要な課税所得の入力としては使わず、別の公式表を採用。

これらのSHA-256は `raw/exploratory/manifest.json` に記録しています。未使用候補の個別ダウンロードURLはこの成果物の記録では確定していないため、再取得パイプラインには含めていません。使用データの再現性には影響しません。画面操作調査用のHTMLやJavaScript、環境依存のライブラリキャッシュは収録対象から除いています。

## v2：性別・最終学歴の追加で使用した統計

追加原表の取得日：2026年9月5日。モデル・検証の更新日：2026年9月6日。

7. **2020国勢調査・就業状態等基本集計11-2**：男女、年齢（5歳階級）、在学か否かの別・最終卒業学校の種類別人口（15歳以上）、全国・都道府県・市区町村。[原Excel](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201217&fileKind=0)、[統計表](https://www.e-stat.go.jp/dbview?sid=0003450543)。`raw/census_education.xlsx` に保存。加工後は `sources/education/census_education_tidy.csv.gz`。
8. **同12-1**：男女、年齢、労働力状態・産業、在学状態・最終卒業学校別人口。全国・都道府県・主要都市等。[原Excel](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201218&fileKind=0)。`raw/census_education_labor.xlsx` に保存。加工時に総数、就業者、完全失業者、非労働力人口、労働力状態不詳を選択。加工後は `sources/education/census_education_labor_tidy.csv.gz`。
9. **2022就業構造基本調査・全国編04000**：男女、配偶関係、年齢、従業上の地位等、所得、教育別人口（有業者）。[統計表](https://www.e-stat.go.jp/dbview?sid=0004008157)。配偶関係総数・従業地位総数を選択し、男女・年齢・所得・教育の表を取得。`raw/education/income_education_{0,1,2}.json.gz`、加工後 `sources/education/income_education_tidy.csv.gz` に保存。

表定義・原ファイル・加工済みファイルのSHA-256は `catalog/education/manifest.json` に記録しています。再取得は `src/fetch_education.py`、加工は `src/parse_education.py`、モデルは `src/build_education.py`、出力は `src/export_education.py`、検証は `src/verify_education.py` です。

学歴の対応付けは[国勢調査公式ユーザーズガイド](https://www.stat.go.jp/data/kokusei/2020/kekka/pdf/u_guide_2020.pdf)と[就業構造基本調査用語解説](https://www.stat.go.jp/data/shugyou/2022/pdf/yougo.pdf)を参照しました。専門学校の修業年数・卒業時期等の対応に近似があることはMETHOD.mdに記載しています。調査結果を加工・推定したもので、政府による市区町村別学歴・所得推計ではありません。

## M2・段階A：産業・就業状態の追加で使用した統計

10. **2020国勢調査・就業状態等基本集計6-3**：男女、年齢（5歳階級）、産業（大分類）別就業者数、全国・都道府県・市区町村。[原Excel](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201184&fileKind=0)。`raw/industry/census_industry_age.xlsx`、加工後 `sources/industry/census_industry_age_tidy.csv.gz`。産業不詳は「分類不能の産業」に含まれる（別列なし）。
11. **2022就業構造基本調査・地域編 表24**：男女、従業上の地位・雇用形態、所得、産業別人口（有業者）、全国・都道府県・主要都市。[原Excel](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040077604&fileKind=0)。`raw/industry/ess_industry_income.xlsx`、加工後 `sources/industry/income_industry_tidy.csv.gz`。年齢区分なし。
12. **2022就業構造基本調査・地域編 表10-1**：男女、在学・卒業、従業上の地位・雇用形態、産業、年齢別人口（有業者）、全国・都道府県・主要都市。[原Excel](https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040077583&fileKind=0)。加工後 `sources/industry/ess_status_industry_age_tidy.csv.gz`。都道府県行は初期値、都市行は検証（開発で使用済み）。
13. **2022就業構造基本調査・全国編04000（従業上の地位別）**：9. と同じ表を自営業主（1）・雇用者（2）・正規（22）・非正規（23）で取得。`raw/industry/education_status_income_*.json.gz`、加工後 `sources/industry/education_status_income_tidy.csv.gz`。
14. **2020国勢調査・就業状態等基本集計 不詳補完結果 参考表1**（2. と同じ表）の完全失業者数・非労働力人口：段階Aの就業状態 J2/J3（地位 K6/K7）の市区町村 × 性別 × 年齢の周辺。学歴との関連の初期値は 8. の労働力状態 12（完全失業者）・2（非労働力人口）。

表定義・原ファイル・加工済みファイルのSHA-256は `catalog/industry/manifest.json` に記録しています。取得は `make fetch-industry`（6-3、表24）と `make fetch-employment`（10-1、04000 地位別）。段階Aの設計・検証・配布形式は `docs/EMPLOYMENT_A.md`。
