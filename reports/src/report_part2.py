"""Chapters 4–9 and appendices. Imported by report_v2_data.py."""


def build(ctx):
    h1, h2, h3 = ctx["h1"], ctx["h2"], ctx["h3"]
    p, bl, nb = ctx["p"], ctx["bl"], ctx["nb"]
    note, code, table, img, shot = (
        ctx["note"],
        ctx["code"],
        ctx["table"],
        ctx["img"],
        ctx["shot"],
    )
    num, pct, df, NAME, ORDER = (
        ctx["num"],
        ctx["pct"],
        ctx["df"],
        ctx["NAME"],
        ctx["ORDER"],
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 4. Hiện thực hóa hệ thống")

    h2("4.1. Cấu trúc mã nguồn")
    p(
        "Repo theo mô hình monorepo: ba dịch vụ backend, một frontend, một gói dùng chung và một thư mục "
        "script vận hành. Gói shared được cài bằng pip install -e nên ba dịch vụ dùng chung đúng một định "
        "nghĩa schema, một lớp truy cập cơ sở dữ liệu và một bộ tiện ích."
    )
    code(
        [
            "NCKH/",
            "├─ AGENTS.md                  # quy tắc dự án — nguồn sự thật duy nhất",
            "├─ docker-compose.yml         # 9 dịch vụ cho môi trường phát triển",
            "├─ configs/group_dataset.json # hợp đồng dữ liệu đã khóa",
            "├─ infra/postgres/init.sql    # 3 schema, 14 bảng, hypertable, ràng buộc",
            "├─ shared/                    # gói dùng chung (pip install -e)",
            "│   ├─ config/settings.py     #   pydantic-settings đọc .env",
            "│   ├─ dataset/loader.py      #   nạp & xác thực snapshot đã khóa",
            "│   ├─ db/                    #   ORM, session, repository",
            "│   └─ schemas/               #   OHLCV, predict (dùng cho cả FE và BE)",
            "├─ services/",
            "│   ├─ ingestion/             # adapters, Celery tasks, beat",
            "│   ├─ training/              # 4 entrypoint + benchmark evaluator",
            "│   └─ inference/             # FastAPI, model_loader, predictors, features",
            "├─ frontend/                  # Next.js App Router + ECharts",
            "├─ scripts/                   # backfill, export/import snapshot, kiểm tra dữ liệu",
            "└─ docs/                      # kiến trúc, API, dataset, protocol, audit, sprint log",
        ],
        "Mã nguồn 4.1 — Cấu trúc thư mục thực tế của repo.",
    )
    table(
        ["Thành phần", "Số tệp", "Số dòng", "Ngôn ngữ"],
        [
            ["services/training", "25", "11.312", "Python"],
            ["shared", "18", "2.370", "Python"],
            ["services/ingestion", "14", "2.259", "Python"],
            ["services/inference", "10", "2.159", "Python"],
            ["scripts", "8", "1.944", "Python"],
            ["tests (mức repo)", "6", "1.071", "Python"],
            ["frontend", "7", "1.494", "TypeScript / TSX"],
        ],
        [40, 16, 18, 26],
        "Bảng 4.1. Quy mô mã nguồn theo thành phần.",
        right=[1, 2],
    )

    h2("4.2. Dịch vụ thu thập dữ liệu")
    p(
        "Mỗi nguồn dữ liệu có một adapter riêng, cùng trả về một kiểu dữ liệu đã chuẩn hóa (OHLCVCreate). "
        "Phần còn lại của hệ thống vì thế không biết dữ liệu đến từ vnstock hay Binance — thêm một sàn mới "
        "chỉ là thêm một adapter, không sửa tầng lưu trữ hay tầng huấn luyện."
    )
    code(
        [
            "class BinanceAdapter:",
            '    """Adapter to fetch historical market data ... using CCXT."""',
            "",
            "    def __init__(self, api_key: str = None, api_secret: str = None):",
            "        # Public endpoints do not require API keys, but authenticated ones do.",
            "        self.exchange = ccxt.binance({",
            '            "apiKey": api_key,',
            '            "secret": api_secret,',
            '            "enableRateLimit": True,     # tôn trọng giới hạn tần suất của sàn',
            "        })",
            "",
            "    def fetch_historical_ohlcv(",
            '        self, symbol: str, timeframe: str = "1h",',
            "        since_timestamp_ms: int = None, limit: int = 100,",
            "    ) -> List[OHLCVCreate]:",
            "        ...",
        ],
        "Mã nguồn 4.2 — services/ingestion/adapters/binance_adapter.py (rút gọn).",
    )
    p(
        "Lịch chạy được khai báo tập trung trong cấu hình Celery Beat; thời điểm chạy bám theo đặc thù thị "
        "trường: crypto giao dịch 24/7 nên lấy theo giờ, cổ phiếu VN chỉ lấy vào cuối phiên các ngày trong tuần."
    )
    code(
        [
            "celery_app.conf.beat_schedule = {",
            '    "ingest-crypto-hourly": {',
            '        "task": "tasks.ingest_crypto_task",',
            '        "schedule": crontab(minute=5),',
            '        "args": (["BTC/USDT", "ETH/USDT"], "1h"),',
            "    },",
            "    # Ngày giao dịch VN: thứ Hai–thứ Sáu, 10:00 UTC = 17:00 giờ Việt Nam",
            '    "ingest-stocks-daily": {',
            '        "task": "tasks.ingest_stocks_task",',
            '        "schedule": crontab(day_of_week="1-5", hour=10, minute=0),',
            '        "args": (["FPT", "VCB", "MSN"], "1d"),',
            "    },",
            "}",
        ],
        "Mã nguồn 4.3 — services/ingestion/celery_app.py: lịch thu thập.",
    )

    h2("4.3. Gói dùng chung và hợp đồng dữ liệu")
    p(
        "Điểm vào của mọi thí nghiệm là hàm assert_locked_dataset(). Hàm này đọc tệp hợp đồng, tính lại "
        "fingerprint của snapshot trên đĩa và so với giá trị đã khóa; sai một byte là dừng ngay, trước khi "
        "bất kỳ mô hình nào được huấn luyện."
    )
    code(
        [
            "def assert_locked_dataset(",
            "    *, contract_path: PathLike = DEFAULT_CONTRACT_PATH,",
            "    snapshot_root: PathLike = DEFAULT_SNAPSHOT_ROOT,",
            ") -> None:",
            '    """Fail fast unless the configured snapshot matches the locked contract."""',
            "    try:",
            "        contract = _load_contract(contract_path)",
            "        _resolve_snapshot_files(contract, snapshot_root)   # kiểm tra checksum từng tệp",
            "    except (OSError, KeyError, TypeError, ValueError) as exc:",
            '        logger.exception("Locked dataset validation failed: %s", exc)',
            "        raise",
            "",
            '    logger.info("Locked dataset validated: version=%s, snapshot=%s",',
            '                contract["dataset_version"], contract["source_snapshot_name"])',
        ],
        "Mã nguồn 4.4 — shared/dataset/loader.py: cổng chặn dữ liệu sai hợp đồng.",
    )

    h2("4.4. Dịch vụ huấn luyện")
    p(
        "Bốn entrypoint độc lập nhưng tuân theo cùng một khung: xác thực dữ liệu → dựng đặc trưng nhân quả → "
        "chia theo thời gian → fit scaler chỉ trên train → huấn luyện với seed cố định → đánh giá một lần trên "
        "test cùng baseline Naive → ghi MLflow → xuất CSV theo đúng schema của protocol."
    )
    p(
        "Ví dụ dưới đây là kiến trúc GRU phiên bản 2. Điểm đáng chú ý về mặt thiết kế: mạng không dự đoán "
        "thẳng mức giá mà dự đoán phần hiệu chỉnh cộng vào giá đóng cửa gần nhất, và lớp ra được khởi tạo "
        "bằng 0 — nghĩa là tại thời điểm bắt đầu huấn luyện, mô hình đúng bằng baseline Naive rồi mới học "
        "dần phần cải thiện."
    )
    code(
        [
            "class GRUForecaster(nn.Module):",
            "    def forward(self, inputs: torch.Tensor) -> torch.Tensor:",
            "        if inputs.ndim != 3 or inputs.shape[-1] != self.input_size:",
            '            raise ValueError("GRU inputs must have shape (batch, sequence, input_size).")',
            "        recurrent_output, _ = self.gru(inputs)",
            "        residual = self.output_layer(recurrent_output[:, -1, :]).squeeze(-1)",
            "        # Residual connection: close price is at index 0",
            "        last_close = inputs[:, -1, 0]",
            "        return last_close + residual",
        ],
        "Mã nguồn 4.5 — services/training/models/gru_model.py: kiến trúc residual.",
    )
    p(
        "Quy tắc chống rò rỉ dữ liệu được đặt ngay trong mã, không nằm ở tài liệu: scaler chỉ nhìn thấy các "
        "dòng thuộc tập train."
    )
    code(
        [
            "def _fit_train_scalers(featured: pd.DataFrame) -> tuple[MinMaxScaler, MinMaxScaler]:",
            '    """Fit feature and target scalers once, using training rows only."""',
            '    train_rows = featured["split"].eq("train")',
            "    feature_scaler = MinMaxScaler()",
            "    target_scaler = MinMaxScaler()",
            "    feature_scaler.fit(featured.loc[train_rows, FEATURE_LIST])",
            "    # Align target scaling exactly with 'close' feature scaling",
            '    target_scaler.fit(featured.loc[train_rows, ["close"]].to_numpy())',
            "    return feature_scaler, target_scaler",
        ],
        "Mã nguồn 4.6 — services/training/train_gru.py: scaler chỉ fit trên tập train.",
    )

    h2("4.5. Dịch vụ dự báo")
    p(
        "Dịch vụ inference không giữ bản sao mô hình nào trong repo. Khi có yêu cầu, nó hỏi MLflow Registry "
        "phiên bản mới nhất của tên mô hình tương ứng rồi nạp về. Có hai đường nạp, và sự tồn tại của đường "
        "thứ hai là một bài học kỹ thuật đáng ghi lại (xem §5.7):"
    )
    code(
        [
            "params = MlflowClient().get_run(run_id).data.params",
            "try:",
            '    model = mlflow.pytorch.load_model(model_uri, map_location="cpu")',
            "except Exception:",
            "    # Lớp mô hình được pickle theo đường import services.training.models.gru_model,",
            "    # vốn không có trong image inference -> dựng lại từ state dict.",
            '    logger.info("Rebuilding GRU from state dict (training package absent).")',
            "    from gru_net import GRUForecaster",
            "",
            "    model = GRUForecaster(",
            '        input_size=int(params.get("input_size", 8)),',
            '        hidden_size=int(params.get("hidden_size", 64)),',
            '        num_layers=int(params.get("num_layers", 1)),',
            '        dropout=float(params.get("dropout", 0.0)),',
            "    )",
            "    state_path = self._download(run_id, GRU_STATE_DICT_ARTIFACT)",
            '    model.load_state_dict(torch.load(state_path, map_location="cpu"))',
        ],
        "Mã nguồn 4.7 — services/inference/model_loader.py: hai đường nạp mô hình GRU.",
    )

    h2("4.6. Giao diện web")
    p(
        "Frontend gọi API qua một lớp client có kiểu dữ liệu rõ ràng; mọi lỗi HTTP được ném thành ApiError "
        "để trang hiển thị đúng trạng thái lỗi thay vì âm thầm thay bằng dữ liệu giả — một quy ước quan "
        "trọng với hệ thống hiển thị số liệu tài chính."
    )
    code(
        [
            "/**",
            " * Typed fetch helpers for the Inference Service API (/api/v1).",
            " * Every helper throws ApiError (with HTTP status) when the response is not OK,",
            " * so pages can render honest error states instead of silent fallbacks.",
            " */",
            'const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";',
            'const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "...";',
            "",
            "export class ApiError extends Error {",
            "  status: number;",
            "  constructor(status: number, message: string) {",
            '    super(message); this.name = "ApiError"; this.status = status;',
            "  }",
            "}",
        ],
        "Mã nguồn 4.8 — frontend/lib/api.ts (rút gọn).",
    )
    if shot(
        "01_dashboard.png",
        "Hình 4.1 — Trang Dashboard: số liệu tổng quan và danh sách mã, đọc từ API thật.",
        600,
    ):
        pass
    shot(
        "04_forecast_chart.png",
        "Hình 4.2 — Trang Dự báo: biểu đồ nến OHLC của ACB kèm đường dự báo 5 bước của mô hình GRU v2.",
        600,
    )
    shot(
        "06_shap.png",
        "Hình 4.3 — Trang giải thích mô hình: mức ảnh hưởng trung bình |SHAP| của từng đặc trưng (XGBoost).",
        600,
    )

    h2("4.7. Quy ước mã nguồn")
    bl(
        "Mọi hàm Python có type hint; hàm/endpoint công khai có docstring nêu rõ đầu vào, đầu ra và điều kiện lỗi."
    )
    bl(
        "Cấu hình đọc qua pydantic-settings từ .env; không hardcode URL, khóa hay đường dẫn."
    )
    bl(
        "Dữ liệu vào/ra của API dùng schema chung trong shared/schemas, tránh lệch hợp đồng giữa frontend và backend."
    )
    bl(
        'Comment giải thích lý do, không mô tả lại thao tác — ví dụ dòng "close price is at index 0" trong Mã nguồn 4.5 '
        "giải thích vì sao thứ tự đặc trưng là một phần hợp đồng của mô hình."
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 5. Tích hợp mô hình học máy vào hệ thống")

    h2('5.1. Khác biệt giữa "chạy được mô hình" và "tích hợp được mô hình"')
    p(
        "Phần lớn khó khăn của đề tài không nằm ở việc huấn luyện một mô hình cho ra số liệu đẹp, mà nằm ở "
        "việc đưa mô hình đó vào một hệ thống đang chạy và giữ cho kết quả còn đúng theo thời gian. Bảng "
        "dưới đây tóm tắt những khác biệt đã thực sự phát sinh trong dự án."
    )
    table(
        ["Khía cạnh", "Khi chạy trong notebook", "Khi tích hợp vào hệ thống"],
        [
            [
                "Dữ liệu",
                "Một tệp CSV cố định trên máy",
                "Cơ sở dữ liệu thay đổi mỗi giờ → phải khóa snapshot có fingerprint",
            ],
            [
                "Đặc trưng",
                "Tính một lần cùng chỗ với huấn luyện",
                "Phải tính lại ở dịch vụ khác, đúng từng công thức và thứ tự cột",
            ],
            [
                "Mô hình",
                "Biến trong bộ nhớ",
                "Artifact có phiên bản, phải tải được từ máy khác, image khác",
            ],
            [
                "Phụ thuộc",
                "Cùng một môi trường",
                "Image phục vụ không có gói huấn luyện → cần đường dựng lại từ state dict",
            ],
            [
                "Sai sót",
                "Thấy ngay khi chạy ô lệnh",
                "Có thể sai âm thầm, trả ra số trông vẫn hợp lý",
            ],
            [
                "Kết quả",
                "Tin vào con số cuối cùng",
                "Phải tái lập được trên máy khác, có checksum để đối chứng",
            ],
        ],
        [16, 36, 48],
        "Bảng 5.1. Những khác biệt đã phát sinh trong quá trình tích hợp.",
    )

    h2("5.2. Vòng đời một mô hình")
    img(
        "d7_vong_doi_model.png",
        "Hình 5.1 — Bảy bước trong vòng đời một mô hình, từ hợp đồng dữ liệu tới bằng chứng nghiên cứu.",
        665,
    )
    p(
        "Quy ước đặt tên trong Registry là {SYMBOL}_{timeframe}_{model} — ví dụ ACB_1d_gru, BTCUSDT_1h_arima. "
        "Nhờ quy ước này, dịch vụ inference suy ra được tên mô hình cần nạp từ chính tham số của yêu cầu, "
        "không cần bảng ánh xạ riêng. Sau khi nạp, đối tượng mô hình được giữ trong RAM theo khóa (tên, "
        "phiên bản) nên chỉ lần gọi đầu tiên phải trả giá tải artifact."
    )
    shot(
        "10_mlflow_run.png",
        "Hình 5.2 — Một run trong MLflow: trạng thái, run ID, commit nguồn, mô hình đã đăng ký, 27 tham số và 9 chỉ số. "
        "Đây chính là dấu vết cho phép tái lập lại đúng kết quả trong Chương 8.",
        600,
    )
    shot(
        "09_mlflow_registry.png",
        "Hình 5.3 — Model Registry: các mô hình đã đăng ký theo quy ước đặt tên.",
        600,
    )

    h2("5.3. Giao thức so sánh dùng chung và cổng kiểm định")
    p(
        "Bốn mô hình do bốn người làm, mỗi người một bộ đặc trưng. Nếu mỗi người tự báo cáo chỉ số của mình "
        "thì các con số không so sánh được với nhau. Nhóm vì vậy khóa một giao thức chung (docs/"
        "experiment_protocol.md) và viết một chương trình kiểm định độc lập để kiểm tra việc tuân thủ."
    )
    table(
        ["Cổng kiểm tra", "Nội dung"],
        [
            ["Trạng thái run", "Cả bốn MLflow run phải ở trạng thái FINISHED"],
            [
                "Tham số bắt buộc",
                "dataset_version, snapshot_name, symbol, timeframe, target, horizon, seed phải khớp hợp đồng",
            ],
            [
                "Manifest chung",
                "Dựng lại danh sách mẫu kiểm tra từ dữ liệu đã khóa và đối chiếu mã băm SHA-256 của cả bốn run",
            ],
            [
                "Đồng nhất theo dòng",
                "Bốn mô hình phải dự báo đúng cùng tập thời điểm, cùng thứ tự, cùng giá hiện tại và giá thực tế",
            ],
            [
                "Tải lại artifact",
                "Nạp lại mô hình từ Registry và kiểm tra nạp được (GRU phải load_state_dict ở chế độ strict)",
            ],
            [
                "Tính lại chỉ số",
                "Tính lại MAE/RMSE/MAPE từ vector dự báo, dung sai 1e-12, thay vì tin vào số đã ghi",
            ],
            [
                "Baseline Naive",
                "Baseline phải được tính lại và trùng khớp giữa bốn run",
            ],
            [
                "Worktree sạch",
                "Từ chối chạy nếu mã nguồn đang có thay đổi chưa commit — để kết quả luôn gắn với một commit cụ thể",
            ],
        ],
        [24, 76],
        "Bảng 5.2. Các cổng kiểm định trước khi một kết quả được coi là chính thức.",
    )
    note(
        [
            "Ý nghĩa thiết kế của cổng này: hệ thống không tin vào con số mà một mô hình tự khai báo. Mọi chỉ "
            "số trong Chương 8 đều được tính lại từ dữ liệu dự báo thô, trên một tập mẫu kiểm tra dựng lại "
            "độc lập. Đây là cách một hệ thống phần mềm bảo vệ tính đúng đắn của thành phần AI bên trong nó."
        ],
        "Vì sao cổng kiểm định quan trọng với đề tài này",
        "ok",
    )

    h2("5.4. Hai sự cố tích hợp có thật")
    p(
        "Hai lỗi dưới đây phát sinh trong đợt demo ngày 16/09 và đã được sửa bằng hai Pull Request riêng. "
        "Nhóm ghi lại vì chúng minh họa chính xác loại rủi ro mà một hệ thống tích hợp AI gặp phải — và "
        "không xuất hiện khi chạy mô hình trong notebook."
    )
    h3("Sự cố 1 — Mô hình đã đăng ký nhưng dịch vụ không đọc được artifact")
    table(
        ["Mục", "Nội dung"],
        [
            [
                "Hiện tượng",
                'Mọi yêu cầu /api/v1/predict trả 503: "No such file or directory: /mlflow/artifacts/…"',
            ],
            [
                "Nguyên nhân",
                "MLflow lưu artifact ở đường dẫn hệ tệp; client nạp mô hình mở trực tiếp đường dẫn đó. "
                "Trong docker-compose, chỉ dịch vụ training được gắn volume chứa artifact, dịch vụ inference thì không",
            ],
            [
                "Vì sao khó thấy",
                "Mô hình đã huấn luyện xong, đã đăng ký thành công, MLflow UI hiển thị đầy đủ — "
                "sai sót nằm hoàn toàn ở tầng triển khai",
            ],
            [
                "Cách sửa",
                "Gắn volume mlflow_data cho dịch vụ inference (và cho cả training lẫn inference ở tệp compose production, nơi thiếu cả hai) — PR #44",
            ],
            [
                "Bài học",
                'Ranh giới "mô hình đã sẵn sàng" và "mô hình phục vụ được" là một vấn đề triển khai, cần được kiểm thử như một tính năng',
            ],
        ],
        [16, 84],
    )
    h3("Sự cố 2 — Thay kiến trúc mô hình làm vỡ hợp đồng đặc trưng phía dịch vụ")
    table(
        ["Mục", "Nội dung"],
        [
            [
                "Hiện tượng",
                'Yêu cầu dự báo với mô hình GRU trả lỗi: "X has 2 features, but MinMaxScaler is expecting 8"',
            ],
            [
                "Nguyên nhân",
                "Phiên bản GRU mới dùng 8 đặc trưng, độ dài chuỗi 7 và đầu ra dạng residual; dịch vụ inference vẫn dựng 2 đặc trưng theo phiên bản cũ",
            ],
            [
                "Rủi ro nghiêm trọng hơn",
                "Đường dự phòng dựng lại mô hình từ state dict trong image production không có phần residual. "
                "Nếu chỉ sửa số lượng đặc trưng, hệ thống sẽ trả về phần hiệu chỉnh (giá trị gần 0) như thể đó là giá — sai hoàn toàn nhưng không báo lỗi",
            ],
            [
                "Cách sửa",
                "Đồng bộ hóa bộ dựng đặc trưng với mã huấn luyện, thêm residual vào lớp mô hình dự phòng, và bổ sung bốn kiểm thử đối chiếu hai phía — PR #45",
            ],
            [
                "Bài học",
                "Thay đổi kiến trúc mô hình phải được coi là thay đổi hợp đồng API: cần kiểm thử ràng buộc hai phía, "
                "nếu không lỗi sẽ biểu hiện dưới dạng một con số trông hợp lý",
            ],
        ],
        [16, 84],
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 6. Kiểm thử và đảm bảo chất lượng")

    h2("6.1. Chiến lược kiểm thử")
    p(
        "Kiểm thử tập trung vào những chỗ mà lỗi khó phát hiện bằng mắt: hợp đồng dữ liệu, ranh giới chia tập "
        "train/test, tính nhất quán của đặc trưng giữa huấn luyện và phục vụ, và hợp đồng API."
    )
    table(
        ["Nhóm", "Số tệp", "Nội dung kiểm thử tiêu biểu"],
        [
            [
                "services/training/tests",
                "6",
                "Chia tập theo thời gian, scaler chỉ fit trên train, schema CSV đầu ra, tính lại chỉ số",
            ],
            [
                "tests (mức repo)",
                "5",
                "Hợp đồng dataset, tiện ích chỉ báo kỹ thuật, tích hợp cơ sở dữ liệu",
            ],
            [
                "services/inference/tests",
                "3",
                "Hợp đồng API, đối chiếu đặc trưng với mã huấn luyện, hành vi predictor",
            ],
            [
                "services/ingestion/tests",
                "3",
                "Adapter, chuẩn hóa múi giờ, tính idempotent khi nạp lại",
            ],
        ],
        [26, 12, 62],
        "Bảng 6.1. Phân bố 17 tệp kiểm thử tự động.",
    )
    p(
        "Ví dụ điển hình cho nhóm kiểm thử quan trọng nhất — kiểm thử đối chiếu (parity test) — được bổ sung "
        "sau Sự cố 2: nó khẳng định bộ dựng đặc trưng của dịch vụ phục vụ cho ra đúng từng giá trị như bộ "
        "dựng đặc trưng của mã huấn luyện, và lớp mô hình dự phòng cho ra đúng kết quả như lớp mô hình gốc "
        "trên cùng một bộ trọng số."
    )

    h2("6.2. Tích hợp liên tục và các cổng chất lượng")
    img(
        "d6_cicd.png",
        "Hình 6.1 — Chuỗi cổng chất lượng từ máy lập trình viên tới nhánh develop.",
        660,
    )
    table(
        ["Công đoạn CI", "Nội dung", "Chặn merge khi"],
        [
            [
                "Lint & Format",
                "ruff check và ruff format --check trên toàn repo",
                "Có cảnh báo lint hoặc sai định dạng",
            ],
            [
                "Python Tests",
                "pytest chạy cùng một dịch vụ PostgreSQL/TimescaleDB thật",
                "Bất kỳ test nào đỏ",
            ],
            [
                "Docker Compose",
                "Kiểm tra cú pháp tệp compose với .env mẫu",
                "Tệp compose không hợp lệ",
            ],
            ["Frontend Build", "next build", "Lỗi biên dịch TypeScript hoặc build"],
        ],
        [20, 50, 30],
        "Bảng 6.2. Bốn công đoạn bắt buộc của CI.",
    )
    p(
        "Ở phía máy cá nhân, pre-commit chạy ruff và gitleaks trước khi commit được tạo. Thiết kế này xuất "
        "phát từ một nhận định thực tế của nhóm: không thể đảm bảo mọi thành viên (và mọi công cụ AI mà họ "
        "dùng) luôn nhớ quy tắc, nên quy tắc phải được cưỡng chế bằng máy. Điều cần đảm bảo không phải là "
        '"ai đó có đọc tài liệu không" mà là "Git có cho merge không".'
    )

    h2("6.3. Kiểm thử thủ công đã thực hiện")
    p(
        "Ngoài kiểm thử tự động, nhóm đã chạy một đợt kiểm thử hệ thống đầy đủ ngày 16/09/2026 trên một máy "
        "dựng lại từ đầu:"
    )
    table(
        ["Hạng mục kiểm thử", "Cách kiểm", "Kết quả"],
        [
            [
                "Dựng toàn hệ thống từ máy sạch",
                "docker compose up --build",
                "Đạt — 9 container, health check xanh",
            ],
            [
                "Nạp dữ liệu và kiểm tra hợp đồng",
                "import_dataset_snapshot.py + check_group_dataset.py",
                "Đạt — 192.740 dòng, fingerprint khớp",
            ],
            [
                "Huấn luyện 4 mô hình",
                "Bốn entrypoint trên ACB 1d",
                "Đạt — 4 run FINISHED, đăng ký thành công",
            ],
            ["So sánh bốn mô hình", "benchmark evaluator", "Đạt — 4/4 hợp lệ"],
            [
                "API dự báo",
                "POST /predict cho từng mô hình",
                "3/4 đạt ban đầu; GRU đạt sau PR #45",
            ],
            [
                "Giao diện web",
                "Thao tác thủ công trên 4 trang",
                "Đạt — biểu đồ và bảng hiển thị dữ liệu thật",
            ],
        ],
        [30, 38, 32],
        "Bảng 6.3. Kết quả kiểm thử hệ thống ngày 16/09/2026.",
    )

    h2("6.4. Khoảng trống đang được bổ sung")
    p(
        "Ba hạng mục sau chưa có số liệu và đang được một thành viên thực hiện trong tuần này; báo cáo cuối "
        "sẽ bổ sung kết quả:"
    )
    bl(
        "Độ phủ kiểm thử theo từng dịch vụ (hiện mới biết số lượng test, chưa đo coverage)."
    )
    bl(
        "Độ trễ API: đo p50/p95/p99 cho từng mô hình, tách riêng trường hợp cache nguội và cache nóng — "
        "để trả lời tiêu chí p95 ≤ 2 giây."
    )
    bl(
        "Tỷ lệ job thu thập thành công trong ít nhất 24 giờ chạy liên tục — để trả lời tiêu chí ≥ 95 %. "
        "Hạng mục này gắn với việc bổ sung luồng ghi bảng ops.job_log."
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 7. Quy trình phát triển")

    h2("7.1. Nhịp làm việc")
    p(
        "Dự án chia thành các sprint hai tuần, mỗi sprint có mục tiêu, backlog, sản phẩm demo được và họp "
        "rút kinh nghiệm. Việc phân công đã thay đổi so với kế hoạch ban đầu: thay vì chia theo tầng kỹ "
        "thuật, nhóm chia theo mô hình — mỗi thành viên phụ trách trọn gói một mô hình gồm đặc trưng, mã "
        "huấn luyện, entrypoint và kiểm thử riêng (xem ADR-04). Hai thành viên phụ trách frontend."
    )

    h2("7.2. Quản lý mã nguồn")
    table(
        ["Quy tắc", "Hiện trạng"],
        [
            [
                "Nhánh main ← develop ← feature/*",
                "Tuân thủ; không có commit đẩy thẳng vào main",
            ],
            ["Mọi thay đổi qua Pull Request", "45 PR đã hợp nhất tính đến 22/09/2026"],
            ["CI xanh mới được merge", "Tuân thủ — 4 công đoạn bắt buộc"],
            ["Conventional Commits", "Tuân thủ (feat/fix/docs/chore/test)"],
            ["CODEOWNERS tự gán người review", "Đã cấu hình theo thư mục sở hữu"],
            [
                "Ít nhất một người khác review",
                "Chưa tuân thủ triệt để — PR #44 và #45 được hợp nhất khi chỉ có một người, cần khắc phục ở giai đoạn cuối",
            ],
        ],
        [34, 66],
        "Bảng 7.1. Mức độ tuân thủ quy tắc Git.",
    )

    h2("7.3. Quy tắc sử dụng công cụ AI")
    p(
        "Đây là một phần thuộc chính nội dung nghiên cứu của đề tài (quy trình phát triển phần mềm hiện đại), "
        "nên nhóm quy định rõ và kiểm chứng được:"
    )
    bl(
        "Toàn bộ quy tắc nằm trong một tệp duy nhất ở gốc repo (AGENTS.md); các công cụ khác chỉ có tệp trỏ về."
    )
    bl(
        "Người mở Pull Request chịu trách nhiệm từng dòng mã, kể cả mã do công cụ sinh ra; không giải thích "
        "được thì không merge."
    )
    bl(
        "Cấm công cụ tự ý đổi stack công nghệ, tự tạo kiến trúc mới, hoặc sửa file ngoài phạm vi nhiệm vụ."
    )
    bl(
        "Mã tham khảo từ nguồn ngoài phải được đọc hiểu, viết lại theo stack của nhóm và trích dẫn nguồn."
    )
    bl(
        "Bốn tầng bảo đảm: tệp quy tắc → tệp trỏ về cho từng công cụ → cưỡng chế bằng pre-commit và CI → "
        "review của con người. Ba tầng đầu chạy không cần ai nhớ quy tắc."
    )

    h2("7.4. Bằng chứng và khoảng trống")
    p(
        "Nhật ký sprint 1–4 đã có trong docs/sprint-logs/, được tái dựng từ lịch sử commit, Pull Request và "
        "issue — phần tái dựng được ghi chú rõ ở đầu mỗi tệp. Nhật ký các sprint còn lại, cùng biểu đồ "
        "velocity và burndown, đang được bổ sung. Nhóm cũng ghi nhận một hạn chế trung thực: lịch sử commit "
        "tập trung ở một tài khoản Git, nên đóng góp của từng thành viên chưa truy vết được đầy đủ qua Git."
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 8. Kết quả thực nghiệm")

    h2("8.1. Vai trò của chương này")
    p(
        "Chương này không nhằm chứng minh một mô hình học máy vượt trội, mà nhằm trả lời câu hỏi kỹ thuật "
        "phần mềm: hệ thống đã dựng có cho ra kết quả nhất quán, tái lập được và kiểm chứng được hay không. "
        "Toàn bộ số liệu dưới đây được sinh trong một phiên làm việc ngày 16/09/2026, trên một máy dựng lại "
        "từ đầu, và có thể tái lập bằng các lệnh ở Phụ lục B."
    )

    h2("8.2. Thiết lập thí nghiệm")
    table(
        ["Thuộc tính", "Giá trị"],
        [
            ["Phiên bản dữ liệu", "group_dataset_v1, snapshot ohlcv_full_current"],
            ["Mục tiêu dự báo", "next_close, horizon = 1"],
            [
                "Chia dữ liệu",
                "Theo thời gian, không xáo trộn: train 70 % / validation 15 % / test 15 %",
            ],
            ["Seed", "42 cho cả bốn mô hình"],
            ["Baseline bắt buộc", "Naive: giá dự báo = giá đóng cửa hiện tại"],
            [
                "Số bộ dữ liệu",
                "9 (5 cổ phiếu VN khung ngày, 3 cặp crypto khung ngày, 1 cặp crypto khung giờ)",
            ],
            ["Số thí nghiệm", "36 MLflow run (4 mô hình × 9 bộ dữ liệu)"],
        ],
        [24, 76],
        "Bảng 8.1. Thiết lập chung của toàn bộ thí nghiệm.",
    )

    h2("8.3. Kết quả trên bộ dữ liệu chuẩn (ACB, khung 1 ngày)")
    acb = df[df.key == "ACB 1d"].sort_values("rmse")
    rows = []
    for rank, (_, r) in enumerate(acb.iterrows(), 1):
        cmp_ = (
            "Tăng từ hạng 4 — phiên bản kiến trúc mới"
            if r.model == "gru"
            else "Tái lập đúng kết quả tháng 7 (lệch < 1e-12)"
        )
        rows.append(
            {
                "c": [
                    str(rank),
                    NAME[r.model],
                    num(r.mae),
                    num(r.rmse),
                    num(r.mape_pct, 2),
                    num(r.directional_accuracy, 3),
                    pct(r.improvement_vs_naive_rmse_pct),
                    cmp_,
                ],
                "fill": "E9F5EC" if r.model == "gru" else None,
            }
        )
    n0 = acb.iloc[0]
    rows.append(
        [
            "—",
            "Naive (giá hiện tại)",
            num(n0.naive_mae),
            num(n0.naive_rmse),
            num(n0.naive_mape_pct, 2),
            "—",
            "0",
            "Mốc so sánh bắt buộc",
        ]
    )
    table(
        [
            "Hạng",
            "Mô hình",
            "MAE",
            "RMSE",
            "MAPE (%)",
            "Dir. Acc.",
            "Δ RMSE vs Naive",
            "So với tháng 07/2026",
        ],
        rows,
        [7, 16, 10, 10, 9, 9, 13, 26],
        "Bảng 8.2. Kết quả chính thức trên ACB 1d, 78 mẫu kiểm tra, đã qua toàn bộ cổng kiểm định (4/4 hợp lệ).",
        right=[2, 3, 4, 5, 6],
    )
    p(
        [
            {
                "t": "Kết luận quan trọng nhất của bảng trên không phải thứ hạng, mà là: ",
                "b": False,
            },
            {
                "t": "ba mô hình được huấn luyện lại trên máy khác, image Docker khác, cho ra đúng con số của tháng 7 "
                "tới sai số dưới 1e-12",
                "b": True,
            },
            {
                "t": ". Đây là bằng chứng trực tiếp cho thấy đường ống huấn luyện của hệ thống là tất định và hợp "
                "đồng dữ liệu hoạt động đúng như thiết kế."
            },
        ]
    )

    h2("8.4. Mở rộng sang chín bộ dữ liệu")
    img(
        "chart_rmse_ratio.png",
        "Hình 8.1 — Tỷ số RMSE của mỗi mô hình so với baseline Naive (thang log). Cột dưới mức 1× là tốt hơn Naive.",
        660,
    )
    per = []
    for k in ORDER:
        g = df[df.key == k].sort_values("rmse")
        best = g.iloc[0]
        beaters = [NAME[m] for m in g[g.improvement_vs_naive_rmse_pct > 0].model]
        d = 1 if best.rmse >= 100 else 4
        per.append(
            [
                k,
                str(int(best.n_samples)),
                NAME[best.model],
                num(best.rmse, d),
                num(best.naive_rmse, d),
                pct(best.improvement_vs_naive_rmse_pct),
                ", ".join(beaters) if beaters else "Không có",
            ]
        )
    table(
        [
            "Bộ dữ liệu",
            "Số mẫu",
            "Mô hình tốt nhất",
            "RMSE",
            "RMSE Naive",
            "Δ vs Naive",
            "Mô hình vượt Naive",
        ],
        per,
        [14, 9, 18, 12, 12, 11, 24],
        "Bảng 8.3. Tóm tắt theo bộ dữ liệu. Bảng chi tiết đủ 36 run ở Phụ lục A.",
        right=[1, 3, 4, 5],
    )

    h2("8.5. Nhận xét kỹ thuật")
    p("Ba quan sát có giá trị kỹ thuật rút ra từ bảng trên:")
    nb(
        "Ở khung 1 ngày, GRU v2 và ARIMA luôn nằm trong khoảng ±5 % quanh baseline Naive. Đây là hành vi "
        "dự đoán được: cả hai đều mô hình hóa phần thay đổi (residual hoặc sai phân) thay vì mức giá tuyệt đối, "
        "nên điểm xuất phát của chúng chính là Naive."
    )
    nb(
        "XGBoost và Random Forest sai lệch rất lớn ở những mã có xu hướng tăng mạnh (FPT, SOLUSDT, BTCUSDT, "
        "ETHUSDT — RMSE gấp 3 đến 15 lần Naive). Nguyên nhân là hai mô hình này dự đoán trực tiếp mức giá, "
        "mà cây quyết định về bản chất không ngoại suy được ra ngoài khoảng giá trị đã thấy khi huấn luyện. "
        "Khi giá trong giai đoạn kiểm tra vượt ra ngoài vùng giá của giai đoạn huấn luyện, dự báo bị chặn lại "
        "ở mức cũ. Đây là lỗi thiết kế cách đặt mục tiêu dự báo, không phải lỗi rò rỉ dữ liệu hay lỗi cài đặt."
    )
    nb(
        "Ở khung 1 giờ (2.627 mẫu kiểm tra), chỉ ARIMA bám sát Naive, còn GRU v2 kém khoảng 21 %. Bộ siêu "
        "tham số của GRU hiện được chọn cho khung ngày (chuỗi 7 bước, trung bình trượt 7 và 14 bước), "
        "chưa phù hợp với đặc tính nhiễu ở tần suất giờ."
    )
    p(
        "Cả ba quan sát đều dẫn tới cùng một hướng xử lý cụ thể, đã đưa vào kế hoạch ở §9.4: đổi mục tiêu dự "
        "báo của hai mô hình cây sang phần chênh lệch hoặc lợi suất, và tinh chỉnh riêng cho khung 1 giờ."
    )

    h2("8.6. Giới hạn của kết quả")
    bl(
        "Kết quả dựa trên một lần chia dữ liệu cố định cho mỗi mã, chưa có lấy mẫu lặp lại."
    )
    bl(
        "Chưa có kiểm định ý nghĩa thống kê (ví dụ Diebold–Mariano), nên chênh lệch nhỏ giữa các hạng liền kề "
        "không nên được diễn giải thành ưu thế thực sự."
    )
    bl(
        "Cổng kiểm định liên mô hình hiện chỉ hỗ trợ bộ ACB khung 1 ngày; tám bộ còn lại đang ở trạng thái "
        "sơ bộ, dù mã băm mẫu kiểm tra của bốn mô hình trên mỗi bộ đã được xác nhận trùng nhau."
    )
    bl(
        "XGBoost chạy với một lần thử Optuna, Random Forest dùng tham số cố định, ARIMA dùng bậc (1,1,1) cố "
        "định — nên các con số phản ánh một cấu hình cụ thể, không phản ánh năng lực tối đa của thuật toán."
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Chương 9. Đánh giá và kế hoạch")

    h2("9.1. Đối chiếu với kế hoạch ban đầu")
    table(
        ["Nhóm", "Nội dung"],
        [
            [
                "Giữ đúng kế hoạch",
                "Toàn bộ stack công nghệ đã chốt (FastAPI, PyTorch là framework học sâu duy nhất, PostgreSQL + TimescaleDB, "
                "Celery + Redis, Next.js + ECharts, Docker, GitHub Actions, Sentry, ruff, pytest); kiến trúc ba dịch vụ; "
                "thiết kế cơ sở dữ liệu ba schema; quy tắc Git và quy tắc dùng AI agent; quy mô dữ liệu vượt yêu cầu "
                "(15 cổ phiếu và 10 cặp crypto so với yêu cầu tối thiểu 10 và 5)",
            ],
            [
                "Mở rộng thêm ngoài kế hoạch",
                "Khóa dữ liệu bằng snapshot có fingerprint; giao thức so sánh dùng chung và chương trình kiểm định độc lập; "
                "bốn báo cáo rà soát phương pháp; bằng chứng có checksum; MLflow (kế hoạch xếp vào phần mở rộng) được dùng đầy đủ; "
                "giải thích mô hình bằng SHAP",
            ],
            [
                "Thay đổi có chủ ý",
                "Loại LSTM khỏi phạm vi, chỉ giữ GRU; nâng XGBoost và Random Forest thành mô hình chính thay vì baseline; "
                "phân công theo mô hình thay vì theo tầng kỹ thuật; nhóm sáu người thay vì năm",
            ],
            [
                "Chưa đạt / chưa làm",
                "Tiêu chí mô hình chính vượt Naive ở ≥ 70 % số mã (hiện 4/9); chưa có thí nghiệm ablation để trả lời câu hỏi "
                "về giá trị của đặc trưng kỹ thuật; thiếu màn hình quản trị (4/5 màn hình); chưa đo p95 và tỷ lệ job thành công; "
                "chưa triển khai lên môi trường cloud; báo cáo tổng kết chưa viết",
            ],
        ],
        [20, 80],
        "Bảng 9.1. Đối chiếu bốn nhóm thay đổi so với kế hoạch tháng 04/2026.",
    )

    h2("9.2. Mức độ đáp ứng tiêu chí nghiệm thu")
    table(
        ["Tiêu chí nghiệm thu", "Yêu cầu", "Hiện trạng", "Đánh giá"],
        [
            [
                "Thu thập tự động",
                "Chạy theo lịch, có log",
                "Celery Beat + Worker vận hành",
                "Đạt",
            ],
            ["Web App", "≥ 5 màn hình chức năng", "4 màn hình", "Chưa đạt"],
            [
                "API dự báo",
                "p95 ≤ 2 giây",
                "Chưa đo chính thức; quan sát 0,3–0,5 s",
                "Chưa kết luận",
            ],
            [
                "Bảo mật tối thiểu",
                "API key, giới hạn tần suất, kiểm tra đầu vào",
                "Đủ ba lớp",
                "Đạt",
            ],
            [
                "Số mô hình",
                "≥ 3 baseline + ≥ 1 mô hình học sâu",
                "Naive + ARIMA + XGBoost + Random Forest + GRU",
                "Đạt",
            ],
            [
                "Bảng so sánh trên cùng tập test",
                "Bắt buộc",
                "Có, kèm cổng kiểm định độc lập",
                "Đạt",
            ],
            ["Ablation", "Ít nhất một thí nghiệm", "Chưa có", "Chưa đạt"],
            [
                "Vượt Naive ở ≥ 70 % số mã",
                "Tiêu chí chính",
                "4/9 bộ dữ liệu (44 %)",
                "Chưa đạt",
            ],
            [
                "Tài liệu",
                "Đủ chương, có trích dẫn, có nhật ký sprint",
                "Tài liệu kỹ thuật đầy đủ; nhật ký sprint mới có 4/12",
                "Một phần",
            ],
        ],
        [26, 24, 34, 16],
        "Bảng 9.2. Đối chiếu với tiêu chí nghiệm thu đã đặt ra trong kế hoạch.",
    )

    h2("9.3. Hạn chế")
    bl(
        "Tiêu chí vượt Naive ở ≥ 70 % số mã chưa đạt. Nguyên nhân đã được chẩn đoán cụ thể (cách đặt mục tiêu "
        "dự báo của hai mô hình cây), nên đây là vấn đề có hướng xử lý rõ ràng chứ không phải bế tắc."
    )
    bl(
        "Một phần thiết kế cơ sở dữ liệu (nhóm bảng ml.*, ops.job_log) chưa có luồng ghi, khiến khả năng quan "
        "sát hệ thống phụ thuộc vào log dạng văn bản."
    )
    bl("Đóng góp của từng thành viên chưa truy vết được đầy đủ qua lịch sử Git.")
    bl(
        "Hệ thống mới chạy trên môi trường phát triển; chưa được triển khai và kiểm chứng trên môi trường thật."
    )

    h2("9.4. Kế hoạch năm tuần còn lại")
    table(
        ["Tuần", "Hạng mục", "Kết quả cần có"],
        [
            [
                "22–28/09",
                "Bộ ảnh minh chứng; đo p95 và tỷ lệ job thành công; độ phủ kiểm thử; nhật ký sprint 5–12",
                "Đủ số liệu cho Chương 6 và Chương 7",
            ],
            [
                "29/09–05/10",
                "Đổi mục tiêu dự báo của XGBoost và Random Forest sang phần chênh lệch/lợi suất; tăng số lần thử Optuna; "
                "Random Forest dùng tập validation; chọn bậc ARIMA bằng AIC",
                "Chạy lại 9 bộ dữ liệu, cập nhật Bảng 8.3",
            ],
            [
                "06–12/10",
                "Tinh chỉnh GRU riêng cho khung 1 giờ; mở rộng cổng kiểm định cho mọi mã và khung thời gian",
                "Kết quả chuyển từ sơ bộ sang chính thức",
            ],
            [
                "13–19/10",
                "Trang quản trị/log; bổ sung luồng ghi ops.job_log; kiểm định Diebold–Mariano",
                "Đủ 5 màn hình; trả lời được câu hỏi nghiên cứu về độ tin cậy",
            ],
            [
                "20–26/10",
                "Hoàn thiện báo cáo tổng kết, đóng gói demo, tổng duyệt",
                "Bản nộp cuối cùng",
            ],
        ],
        [14, 56, 30],
        "Bảng 9.3. Kế hoạch tới mốc kết thúc đề tài.",
    )

    h2("9.5. Kết luận")
    p(
        "Đến thời điểm báo cáo, phần hệ thống — vốn là trọng tâm của đề tài — đã hoàn chỉnh và chạy được "
        "end-to-end: dữ liệu được thu thập tự động, lưu trữ có kiểm soát, khóa lại để nghiên cứu, mô hình "
        "được huấn luyện và phiên bản hóa, dịch vụ dự báo phục vụ được cả bốn mô hình, và giao diện web hiển "
        "thị dữ liệu thật. Quan trọng hơn con số dự báo, hệ thống đã chứng minh được tính tất định: cùng một "
        "quy trình chạy lại trên máy khác cho ra cùng một kết quả."
    )
    p(
        "Phần còn thiếu tập trung ở ba chỗ: chất lượng dự báo của hai mô hình cây (đã có hướng xử lý cụ thể), "
        "các số đo vận hành (đang được thu thập), và một màn hình chức năng. Năm tuần còn lại đủ để khép lại "
        "cả ba, với điều kiện giữ đúng nhịp đã có."
    )

    # ═══════════════════════════════════════════════════════════════
    h1("Phụ lục A. Bảng kết quả chi tiết 36 thí nghiệm")
    p(
        "Mỗi dòng tương ứng một MLflow run. Δ RMSE so với Naive = (RMSE_naive − RMSE_model) / RMSE_naive × 100; "
        "giá trị dương nghĩa là tốt hơn baseline. Dòng in đậm là mô hình tốt nhất của bộ dữ liệu đó. Với các "
        "mã có giá trị lớn (BTCUSDT, ETHUSDT), MAE và RMSE được làm tròn tới một chữ số thập phân.",
        size=19,
    )
    full = []
    for k in ORDER:
        g = df[df.key == k].sort_values("rmse")
        best_model = g.iloc[0].model
        for _, r in g.iterrows():
            d = 1 if r.rmse >= 100 else 4
            cells = [
                r.symbol,
                r.timeframe,
                NAME[r.model],
                str(int(r.n_samples)),
                num(r.mae, d),
                num(r.rmse, d),
                num(r.mape_pct, 2),
                num(r.directional_accuracy, 3),
                num(r.naive_rmse, d),
                num(r.improvement_vs_naive_rmse_pct, 2),
            ]
            full.append(
                {"c": cells, "fill": "EFF6EF" if r.model == best_model else None}
            )
    table(
        [
            "Mã",
            "Khung",
            "Mô hình",
            "n",
            "MAE",
            "RMSE",
            "MAPE (%)",
            "Dir. Acc.",
            "Naive RMSE",
            "Δ vs Naive (%)",
        ],
        full,
        [9, 7, 15, 6, 11, 11, 10, 9, 11, 11],
        None,
        right=[3, 4, 5, 6, 7, 8, 9],
        size=16,
    )

    h1("Phụ lục B. Hướng dẫn tái lập")
    p(
        "Các lệnh dưới đây dựng lại toàn bộ hệ thống và sinh lại số liệu của Chương 8 trên một máy sạch có "
        "Docker."
    )
    code(
        [
            "# 1. Dựng hệ thống",
            "git clone <repo> && cd NCKH && cp .env.example .env",
            "docker compose up -d --build",
            "",
            "# 2. Nạp dữ liệu đã khóa và kiểm tra hợp đồng",
            "docker compose run --rm -w /app training \\",
            "    python scripts/import_dataset_snapshot.py \\",
            "    --snapshot-dir data/snapshots/ohlcv_full_current --replace",
            "docker compose run --rm -w /app training python scripts/check_group_dataset.py",
            "",
            "# 3. Huấn luyện (lặp lại cho xgboost, random_forest, gru)",
            "docker compose run --rm training python train_arima.py --ticker ACB --timeframe 1d",
            "",
            "# 4. Chạy cổng kiểm định với bốn run ID thu được ở bước 3",
            "docker compose run --rm -w /app training python -m services.training.benchmark \\",
            "    --xgboost-run-id <id> --random-forest-run-id <id> \\",
            "    --gru-run-id <id> --arima-run-id <id> \\",
            "    --output-dir artifacts/benchmarks/ACB_1d",
            "",
            "# 5. Gọi thử API dự báo",
            "curl -X POST http://localhost:8000/api/v1/predict \\",
            '    -H "Content-Type: application/json" -H "X-API-Key: <khóa trong .env>" \\',
            '    -d \'{"ticker_id":"ACB","model_name":"gru","steps":3,"timeframe":"1d"}\'',
        ],
        "Mã nguồn B.1 — Trình tự tái lập đầy đủ.",
    )
    p(
        "Kết quả của mỗi run nằm ở artifacts/metrics/<mô hình>/<mã>_<khung>_<run_id>.csv và "
        "artifacts/predictions/<mô hình>/…; bằng chứng benchmark kèm checksum nằm ở docs/evidence/."
    )
    table(
        ["Tài liệu trong repo", "Nội dung"],
        [
            ["AGENTS.md", "Quy tắc dự án và quy tắc sử dụng công cụ AI"],
            ["docs/architecture.md", "Kiến trúc hệ thống"],
            ["docs/api.md", "Hợp đồng API"],
            ["docs/dataset.md", "Quy ước dataset và snapshot khóa"],
            ["docs/experiment_protocol.md", "Giao thức so sánh bốn mô hình"],
            ["docs/experiment_report.md", "Báo cáo thí nghiệm ACB 1d tháng 07/2026"],
            ["docs/audit/*.md", "Bốn báo cáo rà soát phương pháp luận của bốn mô hình"],
            ["docs/sprint-logs/", "Nhật ký Agile theo sprint"],
        ],
        [30, 70],
        "Bảng B.1. Tài liệu kèm theo mã nguồn.",
    )
