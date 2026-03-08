# 必須DBテーブルとカラム一覧 (OES連携・生データ完全保存版)

#### 作成日
2025年1月

#### 概要
このツール（客層別最適化メニュー生成システム）を使用するために **必ず必要な** テーブルとカラムをまとめたドキュメントです。
分析用のテーブル群に加え、**OES（オーダーエントリーシステム）の生データを1カラムの漏れもなく全て保存する7つの物理テーブル**を追加しています。

--------------------------------------------------------------------------------

#### 1. 必須テーブル一覧（19テーブル）

##### 1.1 基本マスタテーブル（3テーブル）
| テーブル名 | 用途 | 必須度 |
| ------ | ------ | ------ |
| chains | チェーンマスタ | **必須** |
| stores | 店舗マスタ | **必須** |
| items | 商品マスタ | **必須** |

##### 1.2 来店・注文テーブル（4テーブル）
| テーブル名 | 用途 | 必須度 |
| ------ | ------ | ------ |
| customers | 顧客マスタ | **必須** |
| visits | 来店ログ | **必須** |
| orders | 注文ログ | **必須** |
| order_items | 注文明細 | **必須** |

##### 1.3 在庫・設定テーブル（2テーブル）
| テーブル名 | 用途 | 必須度 |
| ------ | ------ | ------ |
| inventory_snapshots | 在庫スナップショット | **必須** |
| store_settings | 店舗設定 | **必須** |

##### 1.4 メニュー生成テーブル（3テーブル）
| テーブル名 | 用途 | 必須度 |
| ------ | ------ | ------ |
| visit_conditions | 来客条件入力ログ（天気・客層など） | **必須** |
| generated_menus | 生成メニューの親レコード（設定情報） | **必須** |
| menu_candidates | 類似度上位商品の候補ログ | **必須** |
| menu_items | 最終決定した上位商品の表示順・実績 | **必須** |

##### 1.5 OES生データ保存テーブル（7テーブル）
OESから連携された通信データを、欠損なく1次保存するためのテーブル群です。
| テーブル名 | 用途 | 必須度 |
| ------ | ------ | ------ |
| oes_order_infos | OESオーダー情報 (HTTPリクエストの生データ) | **必須** |
| oes_accounting_infos | OES会計情報 | **必須** |
| oes_order_registration_headers | OESオーダ登録情報(ヘッダ) | **必須** |
| oes_order_registration_details | OESオーダ登録情報(明細部グランド) | **必須** |
| oes_order_registration_sub_details | OESオーダ登録情報(明細部サブ) | **必須** |
| oes_order_registration_additional_infos | OESオーダ登録情報(付加情報) | **必須** |
| oes_order_registration_customer_infos | OESオーダ登録情報(お客様情報) | **必須** |

--------------------------------------------------------------------------------

#### 2. 必須テーブル定義（詳細）

##### 2.1 基本マスタテーブル
**【chains (チェーンマスタ)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| chain_id | UUID | PK | チェーン一意識別子 |
| chain_code | TEXT | NOT NULL, UNIQUE | 企業コード |
| chain_name | TEXT | NOT NULL | チェーン名 |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 更新日時 |

**【stores (店舗マスタ)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| store_id | INTEGER | PK | OES店舗ID (CSVの1列目そのまま: 4, 16等) |
| chain_id | UUID | FK | `chains.chain_id` |
| store_name | TEXT | NOT NULL | 店舗名 |
| shop_code | TEXT | UNIQUE | 5桁の店舗コード (例: 00086) |
| oes_shop_id | INTEGER | | OES連携用店舗ID |
| area_layer_name | TEXT | | エリア層名（エリアフィルタリング用。例: 関東、関西） |
| created_at | TIMESTAMPTZ | | 登録日時 |
| updated_at | TIMESTAMPTZ | | 更新日時 |

**【items (メニューマスタ)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| item_id | INTEGER | PK | メニュー一意識別子 |
| store_id | INTEGER | NOT NULL, FK | `stores.store_id` |
| name | TEXT | NOT NULL | メニュー名称 |
| base_price | INTEGER | | 基本単価 |
| grand_menu_no | TEXT | | OESのメニューNo (5桁) と紐付け |
| category_large | TEXT | | 大カテゴリ |
| category_medium| TEXT | | 中カテゴリ |
| category_small | TEXT | | 小カテゴリ |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | 有効フラグ |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 更新日時 |

---

##### 2.2 来店・注文テーブル (OES連携コア)
**【customers (顧客マスタ)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| customer_id | UUID | PK | 顧客一意識別子 |
| name | TEXT | | 顧客名 |
| email | TEXT | | メールアドレス |
| phone | TEXT | | 電話番号 |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 更新日時 |

**【visits (来店・伝票テーブル)】**
1回の来店（1伝票）を表します。OESの「ヘッダ部」および「付加情報部」のデータを集約します。
| カラム名 | データ型 | 制約 | 備考 (OESデータソース) |
| :--- | :--- | :--- | :--- |
| visit_id | UUID | PK | 来店一意識別子 |
| store_id | INTEGER | FK | `stores.store_id` |
| customer_id | UUID | FK | `customers.customer_id` |
| receipt_no | TEXT | NOT NULL | 伝票番号 (OESヘッダ部 / 6桁) |
| table_number | TEXT | | テーブル番号 (末尾アンダースコアトリム) |
| party_size | INTEGER | | 人数1 (客数) |
| customer_layer | TEXT | | 客層1～2 |
| visit_time | TIMESTAMPTZ | | **【入店時間】** スタート日時 |
| leave_time | TIMESTAMPTZ | | **【退店時間】** info_type=2(会計)のOrder情報日時 |
| party_start_time | TIMESTAMPTZ| | **【宴会】** 宴会開始時間 (付加情報) |
| party_end_time | TIMESTAMPTZ | | **【宴会】** 宴会終了予定時間 (付加情報) |
| buffet_start_time| TIMESTAMPTZ| | **【飲み放題】** 開始時間 (付加情報) |
| buffet_end_time | TIMESTAMPTZ | | **【飲み放題】** 終了時間 (付加情報) |
| attributes | JSONB | | その他属性 (会計方式, 伝票種別, 予約有無, 予算など) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |

**【orders (オーダー送信履歴テーブル)】**
1回の注文送信（ハンディ等からの送信単位）を表します。
| カラム名 | データ型 | 制約 | 備考 (OESデータソース) |
| :--- | :--- | :--- | :--- |
| order_id | UUID | PK | 送信単位の識別子 |
| visit_id | UUID | FK | `visits.visit_id` (伝票番号で紐付け) |
| store_id | INTEGER | FK | `stores.store_id` |
| info_seq | INTEGER | | OES通知シリアルNO (CSV 2列目) |
| order_time | TIMESTAMPTZ | | **【注文時間】** 受付日時 または CSV5列目の日時 |
| cook_comp_time | TIMESTAMPTZ | | **【調理】** 注文全体の調理完了日時 |
| serve_comp_time | TIMESTAMPTZ| | **【提供】** 注文全体の提供完了日時 |
| all_serve_comp_time| TIMESTAMPTZ| | **【全提供】** 全メニュー提供完了日時 |
| order_type | INTEGER | | オーダ種別1 (0:新規, 1:追加) |
| input_type | INTEGER | | 入力オーダ判定 (0:自動, 1:POS, 2:HT, 3:MD) |
| terminal_no | TEXT | | 端末番号 |
| total_amount | DECIMAL(10,2) | NOT NULL | 合計金額 (明細合計から算出) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |

**【order_items (注文明細テーブル)】**
1回のオーダーに含まれる各メニューの明細を表します。
| カラム名 | データ型 | 制約 | 備考 (OESデータソース) |
| :--- | :--- | :--- | :--- |
| order_item_id | UUID | PK | 明細行の識別子 |
| order_id | UUID | FK | `orders.order_id` |
| item_id | INTEGER | FK | `items.item_id` (メニューNoで変換) |
| line_type | TEXT | | 明細区分 (`M`: グランド, `S`: サブ/セット) |
| item_name_raw | TEXT | | メニュー名称 (CSVから取得した生名) |
| quantity | INTEGER | NOT NULL, DEFAULT 1 | 数量 (符号付き) |
| unit_price | DECIMAL(10,2) | NOT NULL | 単価 (符号付き) |
| cook_start_sec | INTEGER | | **【時間】** 調理開始指示時間 (秒) |
| cook_comp_sec | INTEGER | | **【時間】** 調理完了時間 (秒) |
| serve_comp_sec | INTEGER | | **【時間】** 提供完了時間 (秒) |
| attributes | JSONB | | サブ情報 (セットコース名称, 正負フラグ, 提供時期数量など) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 登録日時 |

---

##### 2.3 在庫・設定テーブル
**【inventory_snapshots (品切れ・在庫情報)】**
| カラム名 | データ型 | 制約 | 備考 (OESデータソース) |
| :--- | :--- | :--- | :--- |
| snapshot_id | UUID | PK | 在庫履歴識別子 |
| store_id | INTEGER | FK | `stores.store_id` |
| item_id | INTEGER | FK | `items.item_id` |
| stock_status | TEXT | | 品切れ残数 (`000`:品切れ, `***`:解除, `001~`:残数) |
| status_time | TEXT | | **【時間】** 時刻 (`HHMM` 形式) |
| snapshot_date | DATE | | データ取得日 |
| captured_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 取得日時（アプリの最新スナップ取得用） |
| stock_qty | INTEGER | NOT NULL, DEFAULT 0 | 在庫数量（アプリの候補抽出・スコア用） |
| is_available | BOOLEAN | NOT NULL, DEFAULT true | 提供可否フラグ |

**【store_settings (店舗設定)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| setting_id | UUID | PK | |
| store_id | INTEGER | UNIQUE, FK | `stores.store_id`（1店舗1レコード） |
| menu_total | INTEGER | NOT NULL, DEFAULT 20 | メニュー表示件数 |
| overstock_slots | INTEGER | NOT NULL, DEFAULT 3 | 店長枠の件数 |
| max_per_category | INTEGER | NOT NULL, DEFAULT 6 | 同一カテゴリの上限 |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 更新日時 |

---

##### 2.4 メニュー生成テーブル (類似度・フードロス対応)
来客（`visit_id`）ごとに入力された条件と、生成された上位商品の履歴を管理します。

**【visit_conditions (来客条件入力ログ)】**
メニュー生成時に入力された来客情報をすべて記録します。
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| visit_condition_id | UUID | PK | 生成条件識別子 |
| visit_id | UUID | FK | `visits.visit_id` (来客との紐付け) |
| gender | TEXT | | 性別 |
| age_group | TEXT | | 年齢層 |
| visit_time | TIME | | 来店時間 |
| party_size | INTEGER | | 人数 |
| customer_layer | TEXT | | 客層 |
| weather | TEXT | | 天気 |
| created_at | TIMESTAMPTZ | | 登録日時 |

**【generated_menus (生成メニューの親レコード)】**
1回の生成アクションを管理します。生成メニュー画像のメタデータも保持します（旧 menu_images を統合）。
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| menu_id | UUID | PK | 生成メニュー識別子 |
| store_id | INTEGER | FK | `stores.store_id` |
| visit_id | UUID | FK | `visits.visit_id` |
| visit_condition_id | UUID | FK | `visit_conditions.visit_condition_id` |
| menu_total | INTEGER | | メニュー表示件数 |
| overstock_slots | INTEGER | | 店長枠の件数 |
| context_snapshot | JSONB | | 来客条件スナップ（gender, ageGroup, partySize 等） |
| is_food_loss_enabled| BOOLEAN | DEFAULT FALSE| フードロス設定を行ったかどうか |
| storage_path | TEXT | | 生成メニュー画像のストレージパス |
| storage_url | TEXT | | 生成メニュー画像の表示用URL |
| template_type | TEXT | | テンプレート種別 |
| coordinates | JSONB | | 商品座標情報 |
| background_image_size | JSONB | | 背景画像サイズ |
| items_count | INTEGER | | 画像内商品数 |
| created_at | TIMESTAMPTZ | | 生成日時 |

**【menu_candidates (類似度上位20商品の候補ログ)】**
入力情報から抽出された類似度上位20商品を記録します。
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| candidate_id | UUID | PK | 候補識別子 |
| menu_id | UUID | FK | `generated_menus.menu_id` |
| item_id | INTEGER | FK | `items.item_id` |
| item_name | TEXT | | 抽出された商品名 |
| rank | INTEGER | | 候補内順位 (1〜) |
| similarity_score | FLOAT | | 属性情報との類似度スコア |
| is_food_loss | BOOLEAN | DEFAULT FALSE| フードロス設定により優先抽出された商品か |
| created_at | TIMESTAMPTZ | | 登録日時 |

**【menu_items (最終決定した上位10商品の表示順)】**
候補20商品の中から最終的にメニューとして採用された上位10商品を記録します。OCR座標・クリック数も保持（旧 menu_bboxes / menu_clicks を統合）。
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| menu_item_id | UUID | PK | 採用メニュー識別子 |
| menu_id | UUID | FK | `generated_menus.menu_id` |
| item_id | INTEGER | FK | `items.item_id` |
| item_name | TEXT | | 採用された商品名 |
| similarity_score | FLOAT | | 採用時の類似度スコア |
| source | TEXT | | 出所（'MODEL', 'OVERSTOCK' 等） |
| score | DOUBLE PRECISION | | 採用スコア |
| is_food_loss | BOOLEAN | DEFAULT FALSE| フードロス枠として採用された商品か |
| display_order | INTEGER | | メニュー上での表示順 (1〜10) |
| x1, y1, x2, y2 | DOUBLE PRECISION | | OCRバウンディングボックス座標 |
| click_count | INTEGER | NOT NULL, DEFAULT 0 | クリック数（タブレット用） |
| created_at | TIMESTAMPTZ | | 登録日時 |

---

##### 2.5 OES生データ保存テーブル (完全網羅)
資料に基づき、OESから取得したデータを分解・保存するための全カラムを定義します。（※可読性のため、連続する同種のカラムは一部 `1〜N` の表記でまとめていますが、実際のDBにはすべてのカラムが作成されます）

**【oes_order_infos (OESオーダー情報)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| shop_id | INTEGER | PK | 店舗ID |
| info_seq | INTEGER | PK | 通知シリアルNO |
| created_at | TIMESTAMPTZ | PK | 登録日時 |
| info_type | INTEGER | | HTTPリクエストの機能種別 ID |
| order_info | TEXT | | HTTPリクエストのオーダー情報 |
| order_date | VARCHAR | | HTTPリクエストのオーダー情報日時 |
| status | INTEGER | DEFAULT 0 | 0:未分解, 1:分解完了, 2:分解不要 |
| is_deleted | INTEGER | DEFAULT 0 | 0:未削除, 1:削除 |
| created_by | VARCHAR | NOT NULL | 登録者 |
| updated_by | VARCHAR | | 更新者 |
| updated_at | TIMESTAMPTZ | | 更新日時 |

**【oes_accounting_infos (OES会計情報)】**
| カラム名 | データ型 | 制約 | 備考 |
| :--- | :--- | :--- | :--- |
| id | BIGSERIAL | PK | |
| contract_cd | VARCHAR(12) | NOT NULL | 契約番号 |
| receipt_no | VARCHAR | NOT NULL | 伝票番号 |
| oes_data_created_at | TIMESTAMP | NOT NULL | oes_order_infosテーブルのcreated_at |
| info_type | INTEGER | NOT NULL | HTTPリクエストの機能種別ID |
| created_at | TIMESTAMP | NOT NULL | 登録日時 |
| updated_at | TIMESTAMP | | 更新日時 |

**【oes_order_registration_headers (OESオーダ登録情報: ヘッダ)】**
全84カラムを網羅します。
| カラム名 | データ型 | 備考 |
| :--- | :--- | :--- |
| id | BIGSERIAL (PK) | |
| contract_cd | VARCHAR(12) | 契約番号 |
| receipt_no | VARCHAR(6) | 伝票番号 |
| order_no | VARCHAR(2) | 伝票番号枝番 |
| oes_data_created_at | TIMESTAMP | OESデータ登録日時 |
| data_length | VARCHAR(6) | レングス |
| data_classification | VARCHAR | 終了区分 (C:継続, L:最終) |
| guest_no | VARCHAR(6) | 顧客番号 |
| reservation_no | VARCHAR(3) | 予約番号 |
| order_regist_mode | INTEGER | オーダ種別1 (0:新規, 1:追加) |
| order_type | INTEGER | 一部会計転送種別 |
| order_operation_mode | INTEGER | オペレーションモード |
| em_flg | INTEGER | オーダタイプ (0:通常, 1:従食) |
| delivery_flg | INTEGER | 会計方式 (0:店内, 1:出前) |
| split_flg_and_separate_info| INTEGER | 伝票種別 |
| reservation_flg | INTEGER | 予約有無 |
| party_flg | INTEGER | 宴会設定 |
| order_system | INTEGER | オーダ方式 |
| spare1 〜 spare4 | INTEGER/VARCHAR| 予備領域 |
| buffet_status1 〜 8 | INTEGER | 飲み放題1〜8終了フラグ |
| last_order_type | INTEGER | ラストオーダフラグ |
| account_seq_no | INTEGER | 会計情報フラグ |
| marge_receipt_info | INTEGER | 伝票合算情報フラグ |
| marge_receipt_no1 〜 3| VARCHAR(6) | 登録前伝票番号1〜3 |
| input_device_flg | INTEGER | 入力オーダ判定 (0:自動, 1:POS, 2:HT, 3:MD) |
| terminal_no | VARCHAR(2) | ターミナル番号 |
| menu_version | VARCHAR(10) | メニューバージョン |
| menu_revision | VARCHAR(4) | メニューリビジョン |
| input_emp_no | VARCHAR(8) | 従業員番号 |
| table_no | VARCHAR(12) | テーブル番号 |
| spread_table_no | VARCHAR(12) | 配膳先テーブル番号 |
| emp_no | VARCHAR(8) | 従食従業員番号 |
| tel_no | TEXT | 出前電話番号 |
| member_num1 〜 9 | VARCHAR(4) | 人数1〜9 |
| clientele_code1 〜 2 | VARCHAR(2) | 客層1〜2 |
| division_idx | VARCHAR | 区分 |
| guest_id | VARCHAR(14) | 客ID |
| budget | VARCHAR(7) | 予算金額 |
| order_seq | VARCHAR(4) | 転送通し番号 |
| accept_date | VARCHAR(14) | 受付日時 |
| start_time | VARCHAR(14) | スタート日時 |
| cook_finish_time | VARCHAR(14) | 調理完了日時 |
| spread_finish_time | VARCHAR(14) | 提供完了日時 |
| all_spread_finish_time | VARCHAR(14) | 全メニュー提供完了日時 |
| spare5 | VARCHAR(5) | 予備5 |
| inside_out_total | VARCHAR(7) | 店内飲食（外） |
| inside_in_total | VARCHAR(7) | 店内飲食（内） |
| outside_out_total | VARCHAR(7) | 店内飲食外（外） |
| outside_in_total | VARCHAR(7) | 店内飲食外（内） |
| nt_total | VARCHAR(7) | 非課税 |
| sc1_total | VARCHAR(7) | サービス料・固定額 |
| sc2_total | VARCHAR(7) | サービス料・比率 |
| out_tax1_2_3_total | VARCHAR(7) | 消費税（外） |
| in_tax1_2_3_total | VARCHAR(7) | 消費税（内） |
| order_total | VARCHAR(7) | 転送内合計 |
| total | VARCHAR(7) | 合計 |
| ht_serial_no | VARCHAR(8) | HT機器シリアル番号 |
| settlement_info | VARCHAR | 決済情報 |
| spare6 | VARCHAR(2) | 予備6 |
| menu_record_count | VARCHAR(3) | 明細の数 |
| info_record_count | VARCHAR(2) | 付加情報の数 |
| created_at | TIMESTAMP | 登録日時 |
| updated_at | TIMESTAMP | 更新日時 |

**【oes_order_registration_details (OESオーダ登録情報: 明細部グランド)】**
| カラム名 | データ型 | 備考 |
| :--- | :--- | :--- |
| id | BIGSERIAL (PK) | |
| oes_order_registration_header_id| BIGINT (FK) | ヘッダID |
| seq_idx | VARCHAR(3) | 登録インデックス |
| menu_rec_type | VARCHAR | 明細区分（M:グランドメニュー） |
| set_menu_flg | INTEGER | セットコース区分 |
| spare1, spare2 | INTEGER | 予備1, 予備2 |
| update_flg | INTEGER | 訂正種別 |
| buffet_flg | INTEGER | 飲み放題区分 |
| input_type | INTEGER | 金額区分 |
| to_flg | VARCHAR | テイクアウト区分 |
| menu_serial | INTEGER | 新現旧フラグ |
| day_menu | INTEGER | 日替わり対象メニュー |
| seat_idx | VARCHAR(2) | シート番号 |
| clientele_code1 〜 4 | VARCHAR(2) | 客層1〜4 |
| gm_seq_idx | VARCHAR(3) | グランドメニュー登録インデックス |
| menu_no | VARCHAR(5) | グランドメニュー番号 |
| set_menu_no | VARCHAR(5) | セットコースメニュー番号 |
| spare3, spare4 | VARCHAR(5) | 予備3, 予備4 |
| day_menu_no | VARCHAR(5) | 日替わりメニュー番号 |
| menu_name | VARCHAR(30) | グランドメニュー名称 |
| set_menu_name | VARCHAR(16) | セットコースメニュー名称 |
| a_plus_minus_sign | VARCHAR | 正負フラグ |
| amount | VARCHAR(4) | トータル数量 |
| u_plus_minus_sign | VARCHAR | 単価正負フラグ |
| unit_price | VARCHAR(7) | 単価 |
| service_timing_amount1 〜 10| VARCHAR(4) | 提供時期1〜10数量 |
| spare5 | VARCHAR | 予備5 |
| tax_object_div | INTEGER | 消費税フラグ |
| menu_dtl_to_flg | INTEGER | テイクアウト可否 |
| menu_dtl_sc_flg | INTEGER | サービス料の対象 |
| sc1_flg 〜 sc8_flg | INTEGER | サービス料1〜8 |
| cansel_reason_div | VARCHAR | マイナス理由区分 |
| cansel_reason_code | VARCHAR(2) | マイナス理由 |
| cook_start_time | VARCHAR(5) | 調理開始指示時間 |
| cook_end_time | VARCHAR(5) | 調理完了時間 |
| dish_service_end_time | VARCHAR(5) | 提供完了時間 |
| class1 〜 3 | VARCHAR | 分類コード1〜3 |
| spare6 | VARCHAR(7) | 予備6 |
| created_at, updated_at | TIMESTAMP | 登録日時・更新日時 |

**【oes_order_registration_sub_details (OESオーダ登録情報: 明細部サブ)】**
| カラム名 | データ型 | 備考 |
| :--- | :--- | :--- |
| id | BIGSERIAL (PK) | |
| oes_order_registration_detail_id| BIGINT (FK) | グランドID |
| seq_idx | VARCHAR(3) | 登録インデックス |
| menu_rec_type | VARCHAR | 明細区分（S, X, U） |
| set_menu_flg | INTEGER | セット区分 |
| spare01, update_flg, buffet_flg | INTEGER | 予備・訂正種別・飲み放題区分など |
| input_type, spare02 | INTEGER | 金額区分・予備2 |
| to_flg | VARCHAR | テイクアウト区分 |
| menu_serial | INTEGER | 現旧フラグ |
| spare03 〜 spare07 | VARCHAR | 予備領域 |
| seat_idx | VARCHAR(2) | シート番号 |
| gm_seq_idx | VARCHAR(3) | グランドメニュー登録インデックス |
| menu_no | VARCHAR(5) | グランドメニュー番号 |
| set_menu_no | VARCHAR(5) | セットコースメニュー番号 |
| select_menu_no | VARCHAR(5) | セレクトメニュー番号 |
| sub_select_menu_no | VARCHAR(5) | サブセレクトメニュー番号 |
| spare08 | VARCHAR(5) | 予備8 |
| menu_name | VARCHAR(30) | メニュー名称 |
| spare09 | VARCHAR(16) | 予備9 |
| a_plus_minus_sign | VARCHAR | 正負フラグ |
| amount | VARCHAR(4) | トータル数量 |
| u_plus_minus_sign | VARCHAR | 単価正負フラグ |
| spare10 | VARCHAR | 予備10 |
| unit_price | VARCHAR(6) | 単価 |
| service_timing_amount1 〜 10| VARCHAR(4) | 提供時期1〜10数量 |
| spare11 | VARCHAR | 予備11 |
| tax_object_div 〜 sc8_flg | INTEGER | 消費税フラグ・サービス料各種フラグ |
| spare12, spare13 | VARCHAR | 予備12, 13 |
| cook_start_time | VARCHAR(5) | 調理開始指示時間 |
| cook_end_time | VARCHAR(5) | 調理完了時間 |
| dish_service_end_time | VARCHAR(5) | 提供完了時間 |
| class1 〜 class3 | VARCHAR | 分類コード1〜3 |
| spare14 | VARCHAR(7) | 予備14 |
| created_at, updated_at | TIMESTAMP | 登録・更新日時 |

**【oes_order_registration_additional_infos (OESオーダ登録情報: 付加情報)】**
| カラム名 | データ型 | 備考 |
| :--- | :--- | :--- |
| id | BIGSERIAL (PK) | |
| oes_order_registration_detail_id| BIGINT (FK) | グランドID |
| record_no | VARCHAR(3) | 明細位置インデックス |
| memo_type | INTEGER | 付加情報識別 |
| info_data | VARCHAR(40) | 付加情報 |
| created_at, updated_at | TIMESTAMP | 登録・更新日時 |

**【oes_order_registration_customer_infos (OESオーダ登録情報: お客様情報)】**
| カラム名 | データ型 | 備考 |
| :--- | :--- | :--- |
| id | BIGSERIAL (PK) | |
| oes_order_registration_header_id| BIGINT (FK) | ヘッダID |
| data_length | VARCHAR | レングス |
| guest_name, guest_name2 | TEXT | お客様名称1, 2 (個人情報) |
| guide_time | VARCHAR(14) | 案内日時 |
| spare1 | VARCHAR(3) | 予備1 |
| buffet_menu_no1 〜 8 | VARCHAR(5) | 飲み放題1〜8メニュー番号 |
| buffet_begin_time1 〜 8 | VARCHAR(14) | 飲み放題1〜8開始時間 |
| buffet_finish_time1 〜 8 | VARCHAR(14) | 飲み放題1〜8終了時間 |
| party_start_time | VARCHAR(14) | 宴会開始時間 |
| party_end_time | VARCHAR(14) | 宴会終了時間 |
| subject_div | VARCHAR(2) | クーポン科目区分 |
| coupon_no | VARCHAR(3) | クーポン番号 |
| spare2, spare3 | VARCHAR | 予備2, 3 |
| ff_msg_no1 〜 10 | VARCHAR(2) | 定型メッセージ番号1〜10 |
| memo_file_name_and_free_msg1 〜 3| VARCHAR(40) | フリーメッセージまたは手書きメモ情報1〜3 |
| guest_check_code1 〜 30 | INTEGER | お客様チェック情報1〜30 |
| spare4 | VARCHAR(20) | 予備4 |
| created_at, updated_at | TIMESTAMP | 登録・更新日時 |

--------------------------------------------------------------------------------

#### 3. テーブル間の関係性

```text
chains (1) ──< (N) stores (1) ──< (N) items
                                    │
                                    ├──< (N) inventory_snapshots
                                    │
                                    ├──< (N) order_items
                                    │
                                    └──< (N) menu_items

customers (1) ──< (N) visits (1) ──< (N) visit_conditions
                │                    │
                │                    └──< (N) generated_menus
                │                              │
                │                              ├──< (N) menu_candidates
                │                              │
                │                              └──< (N) menu_items
                │
                └──< (N) orders (1) ──< (N) order_items

stores (1) ──< (1) store_settings


【OES生データ群の関係性】
oes_order_infos (生CSVデータ行)
oes_accounting_infos (会計データ行)

oes_order_registration_headers (1) ──< (N) oes_order_registration_details (グランドメニュー)
                                     │     │
                                     │     ├──< (N) oes_order_registration_sub_details (サブ/セット)
                                     │     │
                                     │     └──< (N) oes_order_registration_additional_infos (付加情報)
                                     │
                                     └──< (N) oes_order_registration_customer_infos (お客様情報)
```

--------------------------------------------------------------------------------

#### 4. 必須インデックス一覧
パフォーマンス向上のための主要なインデックスです。
*(※ 以前のリストに加え、OESテーブル群の複合キーインデックスを追加)*
| テーブル名 | インデックス名 | カラム | 用途 |
| ------ | ------ | ------ | ------ |
| oes_order_infos | oes_order_infos_ix1 | shop_id, info_seq, created_at | OES連携検索 |
| oes_accounting_infos | oes_accounting_info_keys | contract_cd, receipt_no, oes_data_created_at | 会計一意検索 |
| oes_order_registration_headers| oes_order_registration_header_keys| contract_cd, receipt_no, order_no, oes_data_created_at| ヘッダ一意検索 |
| oes_order_registration_details| oes_order_registration_detail_keys| oes_order_registration_header_id, seq_idx | グランド明細一意検索 |
| oes_order_registration_sub_details| oes_order_registration_sub_detail_keys| oes_order_registration_detail_id, seq_idx| サブ明細一意検索 |
| (他、分析用テーブルのインデックス群) | ... | ... | ... |

--------------------------------------------------------------------------------

#### 5. 必須データの初期化
1. **chains** テーブル : 少なくとも1件のチェーンレコードが必要
2. **stores** テーブル : 少なくとも1件の店舗レコードが必要
3. **items** テーブル : 店舗ごとに少なくとも20件以上の商品レコードが必要（is_active = true）

--------------------------------------------------------------------------------

#### 6. まとめ
##### 6.1 必須テーブル数
*   **分析・アプリケーション用**: 12テーブル
*   **OES生データ保存用**: 7テーブル
*   **合計** : 19テーブル

##### 6.2 データ整合性の確保
*   **履歴保護** : 監査・再現性が必要なログ系テーブルは CASCADE を避け、RESTRICT/SET NULL を基本とする。
*   OES生データテーブル群はトランザクションデータとして永久保存またはアーカイブ運用とする。

--------------------------------------------------------------------------------

#### 7. 参考資料
*  テーブル定義SQLファイル: supabase/ ディレクトリ
*  データベース構造整理: documents/DB構造整理.md
