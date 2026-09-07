# 工程間の入出力と再現手順（Issue #34）

本番の最終出力は、ここに書く中間成果物を実際に読み込んで作られます。各工程は推定器の関数（`src/estimator.py`）をそのまま使い、説明のために推定式を別実装していません。中間成果物はデータ領域（`$HINOMOTO_DATA_ROOT/data/`）に保存し、コードリポジトリには入れません。サイトには中間値を配信せず、導出パネルの各工程からこの文書の該当節へリンクします。リンクは公開データの `code_ref`（生成時のコミット）に固定され、main の更新で過去の本番説明が変わることはありません。

## 実行環境と取得

- Python 3.9 以上、`make install`（numpy・pandas）。取得・加工には `make install-source`（openpyxl・xlrd）。
- 入力の固定版：`make dataset`（`catalog/production.json` の固定版アーカイブ。正規化済み入力 `sources/` と公開ページ用 `web/` を取得。約 30 MB）。原表からやり直す場合は `make fetch`（e-Stat から取得。約 400 MB の従業地表を含む）。
- 容量・時間の目安（M2 MacBook 相当）：所得モデルの 4 工程で約 30 秒・43 MB、学歴配分 2 分、段階A 4 分・250 MB、世帯 3 地域 2 分・13 MB、勤務地 1 分・31 MB。

## 所得モデル（M1・M2）：`src/build_production.py`

`python src/build_production.py`（`make build` に含まれる）が 4 工程を順に実行し、`--stage NAME` で保存済みの上流成果物から 1 工程だけを再実行できます。各成果物は `provenance`（モデル・係数・入力の指紋・上流成果物の SHA-256・コード commit・生成時刻）を持ち、指紋・係数・上流が一致しない成果物は読み込みを拒否します（`ValueError`）。`--check` は工程を通した最終配列と `estimator.run()` の直接計算を比較し、差が 1e-9 人以内であることを確認します（同じ numpy 演算を同じ順序で行うため差は 0。許容差は浮動小数点の非決定性のためだけに置く）。結果は `validation/production_stages_check.json`。

| 工程 | 関数 | 入力 | 出力（データ領域） | 次工程 |
|---|---|---|---|---|
| <a id="m1-status"></a>status | `estimator.fit_status`、`status_income_shapes` | 正規化済み入力（国勢調査 参考表1・1-4・5-1、表3-1、就業構造基本調査 02300） | `data/stages/status.npz`：`W[m,s,a,k]` 地位別就業者（人）、`E` 有給就業者、`cp[p,s,a,k,y]` 都道府県 × 地位の所得形状 r(y｜p,s,a,k)（擬似人口 1,000 で平滑化）。2.8 MB | mixture |
| <a id="m1-mixture"></a>mixture | `estimator.mixture`（傾きなし）、`education_tilt`、`industry_tilt`、`mixture`（傾きあり） | status.npz、学歴構成（11-2）、産業構成（6-3）、全国の学歴別・産業別所得形状 | `data/stages/mixture.npz`：`q0[m,s,a,y]` 混合直後の分布（M1 の入力、傾きなし）、`tilt_education` = T_e^γ、`tilt_industry` = T_g^γ₂（係数 0 のときは 1）、`tilt` = 積、`q_tilt` = norm(q0 · tilt)（M2 の入力、校正前）。30 MB | calibrate |
| <a id="m1-calibrate"></a><a id="m2-tilt"></a><a id="m2-calibrate"></a>calibrate | `estimator.calibrate` | mixture.npz、県 × 性別 × 年齢の所得既知の有業者の構成比（02300） | `data/stages/calibrated.npz`：`X_m1` = calibrate(q0)（M1 基準。`model_arrays.npz` を 2e-12 人以内で再現）、`X_m2` = calibrate(q_tilt)（M12 の税務調整前）、`calibration_summary[pref, sex, age, 行和の最大誤差, 列構成比の最大誤差]`。10 MB | finalize |
| <a id="m2-finalize"></a>finalize | `estimator.tax_project`（β=0 では恒等） | calibrated.npz、人口 N | `data/final_arrays.npz`（`counts_by_sex[m,s,a,z]`、z=0 非就業、1..16 年収階級、`provenance` 付き）、`data/model_metadata.json`（係数・入力指紋・各工程の SHA-256・コード commit） | 学歴配分・公開データ |

M1 の公開成果物 `data/model_arrays.npz` は v1 の `src/build.py` が同じ手順（混合 → 県への IPF）で生成しており、工程 calibrate の `X_m1` と一致します（`--check` で確認）。

```sh
make dataset                                  # 固定版の入力
python src/build_production.py                # status → mixture → calibrate → finalize
python src/build_production.py --stage calibrate   # 保存済み mixture.npz から校正だけ再実行
python src/build_production.py --check        # 工程経由と直接計算の一致（1e-9 人）
```

## 学歴別配分（M3）：<a id="m3-education"></a>`src/build_education.py`

`python src/pipeline.py build-education`（`make build` に含まれる）。入力は `final_arrays.npz`（列の周辺）、学歴人数（11-2）、学歴別労働力状態（12-1）、全国の学歴別所得形状（04000）。`build_education.prepare()` が初期値（`shapes`、`rate_array`）を作り、`allocate()` が 8 × 17 の反復比例調整を行う。出力は `data/education_leaf_arrays.npz`（`counts[m,s,a,e,y]`）と `data/municipality_model_v2.npz`。学歴別就業率の初期値（`rate_array`）は `prepare()` の戻り値で、`export_web.py` が公開ページ用に `graph.rates` として配信する（葉の値。学歴人数 0 のセルは 0）。

## 就業状態・地位・産業（M4）：<a id="m4-employment"></a>`src/build_employment.py`

`make build-employment`。入力は `final_arrays.npz`、学歴配分の入力（`build_education.prepare`）、地位別就業者 W（`estimator.fit_status`、status.npz と同じ）、産業別就業者（6-3）、労働力状態（参考表1）、全国・都道府県の関連（04000 地位別、10-1、表24、12-1）。`block()` が市区町村 × 性別 × 年齢ごとに 0 円成分の分割（家族従業／完全失業／非労働力）と 3 周辺の反復比例調整（相対誤差 1e-6、最大 600 回）を行う。出力は `data/employment_a.npz`（対の集計表、193 MB）、`data/employment_a_agg.npz`（全国・都道府県・政令市の集計ブロック、55 MB）、`validation/employment_a_build.json`（反復回数・周辺誤差）。公開ページは葉の市区町村で同じ `block()` の計算を再現し（`tests/web_employment_check.cjs` で照合）、集計地域は集計ブロックを読む。セルごとの反復回数・誤差は葉ではページ内で再計算、集計地域では `employment_a_build.json` の要約のみ。

## 世帯（M5）：<a id="m5-household"></a>`src/build_household.py`、<a id="m5-population"></a>`src/household_sample.py`

`make build-household`（港区・那覇市・遠軽町）。入力は世帯表 9 表（`sources/household/`）。`load_area()` → `aggregate()`（集計表 X の IPF）→ `households()`（世帯人数の 3 制約 KL 射影、続き柄別の期待人数）→ `materialize()`（期待人数表 N・T）。出力 `data/household_b/<code>.npz`（`households[F,s_h,a_h,size]`、`members[F,s_h,a_h,size,role,sex,age]`、`provenance` に入力ファイルの SHA-256）と `validation/household_b_<code>.json`。

`make sample-household`（`household_sample.py --population --sa --link-population --seed 1`）が期待人数表から整数個票 `data/household_b/<code>_population.csv.gz` を抽出し、15 歳以上に段階A のブロックから属性を結びつける。レポート `validation/household_b_population_<code>.json` の `provenance` に上流の期待人数表の SHA-256・seed を記録。`make export-household-web` が要約 `web/household/<code>.json` を作る。

## 勤務地（M6）：<a id="m6-workplace"></a>`src/build_workplace.py`

`make fetch-workplace`（142 表、約 400 MB）→ `make build-workplace`（約 45 秒）→ `make verify-workplace`。`load_inputs()` が OD（第3表）と産業別周辺（第8表）を読み、`seed()` が初期値、`ipf()` が 3 周辺への反復比例調整（許容 0.1 人、1,500 回まで）を行う。出力 `data/workplace_c.npz`（`x[pair,industry]` 最終値、`seed` 初期値、`unknown_workplace`、`provenance`）と `validation/workplace_c_build.json`（反復回数・各周辺の最大誤差・履歴）。全ペア × 全反復は保存しない。検証 `validation/workplace_c_verification.json` と `workplace_c_heldout.csv`（第9・10表の対象地域と各セルの TV）。`make export-workplace-web` が公開用ファイルと、評価対象地域の一覧 `web/workplace/evaluated_areas.json`（`workplace_c_heldout.csv` から生成、手書きの一覧は持たない）を書く。

## 版の対応

`data/model_metadata.json` の `code_commit` と `inputs_fingerprint`、各成果物の `provenance` が対応関係を示す。`export_web.py` は `code_commit` を `graph.json` の `code_ref` に書き、公開ページの再現手順・コード・METHOD へのリンクはその commit に固定される。固定版データの公開は `python src/dataset.py pack` で `sources/` と `web/` を同梱する（中間成果物 `data/stages/` は同梱しない。再現は上記コマンドで行う）。
