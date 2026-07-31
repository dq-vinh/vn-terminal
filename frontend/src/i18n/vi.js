// Vietnamese Dictionary (Externalized Strings)
export default {
  appTitle: "VN Terminal Pro",
  subtitle: "Trạm Nghiên Cứu Chứng Khoán Việt Nam",
  
  // Toolbar
  searchPlaceholder: "Tìm mã CP (ví dụ: FPT, KDH)...",
  timeframe: "Khung thời gian",
  tfDaily: "Ngày (1D)",
  tfWeekly: "Tuần (1W)",
  tfMonthly: "Tháng (1M)",
  dataSource: "Nguồn dữ liệu",
  lastRefresh: "Cập nhật lúc",
  refreshBtn: "Cập nhật EOD",
  saveLayout: "Lưu Giao Diện",
  modelSelect: "Mô hình AI",
  dqValid: "Dữ liệu Hợp lệ",
  dqWarning: "Cảnh báo Dữ liệu",
  dqError: "Lỗi Dữ liệu",
  langToggle: "EN",

  // Right Panel Tabs
  tabIndicators: "Chỉ báo",
  tabStrategies: "Chiến lược",
  tabScreener: "Bộ lọc",
  tabFundamentals: "Tài chính",
  tabAiAnalysis: "Phân tích AI",
  tabDataQuality: "Chất lượng Dữ liệu",

  // Indicators Panel
  indTitle: "Chỉ báo Kỹ thuật",
  smaLabel: "Đường SMA (50, 200)",
  emaLabel: "Đường EMA (20, 50)",
  rsiLabel: "Chỉ số RSI (14)",
  macdLabel: "MACD (12, 26, 9)",
  volumeMaLabel: "Khối lượng MA (20)",
  srLevelsLabel: "Hỗ trợ & Kháng cự (Pivot)",

  // Strategies Panel
  stratTitle: "Thư viện Chiến lược",
  evalBtn: "Đánh giá Tín hiệu",
  scoreLabel: "Điểm số Đạt",
  passedCriteria: "Tiêu chí Đạt",
  failedCriteria: "Tiêu chí Không Đạt",
  targetLevels: "Mức Giá Mục Tiêu & Cắt Lỗ",
  support: "Hỗ trợ",
  resistance: "Kháng cự",
  invalidation: "Cắt lỗ / Vi phạm",

  // Screener Panel
  screenerTitle: "Bộ Lọc Cổ Phiếu Thị Trường",
  exchangeFilter: "Sàn Giao Dịch",
  sectorFilter: "Ngành Nghề",
  minVolume: "KLGD Tối thiểu",
  runScreenerBtn: "Chạy Bộ Lọc",
  exportBtn: "Xuất CSV",
  symbol: "Mã CP",
  closePrice: "Giá Đóng Cửa",
  changePct: "% Thay Đổi",
  volume: "Khối Lượng",
  signal: "Tín Hiệu",

  // Fundamentals Panel
  fundTitle: "Kết Quả Kinh Doanh & Tỷ Suất",
  revenue: "Doanh Thu",
  netIncome: "Lợi Nhuận Sau Thuế",
  grossMargin: "Biên LN Gộp",
  netMargin: "Biên LN Ròng",
  roe: "ROE (%)",
  roa: "ROA (%)",
  viewConsolidated: "Hợp nhất",
  viewSeparate: "Công ty mẹ",
  pubDateWarning: "Thiếu ngày công báo (Chế độ Degraded - không dùng trong Backtest)",

  // AI Panel & 4 Categories
  aiTitle: "Trợ Lý Phân Tích AI",
  aiPromptPlaceholder: "Hỏi AI về mã cổ phiếu này (vd: Phân tích dòng tiền và xu hướng)...",
  sendPromptBtn: "Gửi Câu Hỏi",
  factBundleInspector: "Kiểm tra Tập Dữ Liệu Gốc (Fact Bundle)",
  expandFactDetails: "Xem chi tiết dữ liệu gốc supplied cho AI",
  catFact: "Dữ Liệu Thực Tế (Fact)",
  catCalc: "Kết Quả Tính Toán (Calculated)",
  catInference: "Dự Đoán AI (AI Inference)",
  catUnverified: "Chưa Xác Minh / Thiếu (Unverified)",
  scenarios: "Kịch Bản Xu Hướng",
  baseCase: "Kịch bản Cơ sở",
  bullCase: "Kịch bản Tích cực",
  bearCase: "Kịch bản Tiêu cực",
  confidence: "Độ tin cậy AI",
  sources: "Nguồn tham chiếu",

  // Data Quality Panel
  dqTitle: "Nhật Ký & Kiểm Trát Dữ Liệu",
  ohlcCheck: "Kiểm tra Giá High/Low/Open/Close",
  terminalZeroVol: "Cổ phiếu Tạm ngừng / Hủy niêm yết",
  freshnessStatus: "Trạng thái Cập nhật",
  anomalyCount: "Số lỗi ghi nhận",

  // Bottom Workspace Tabs
  tabWatchlist: "Danh mục Theo dõi",
  tabCurrentSignals: "Tín hiệu Hiện tại",
  tabSignalHistory: "Lịch sử Tín hiệu",
  tabBacktestTrades: "Lịch sử Giao dịch Backtest",
  tabEquityCurve: "Đường Cong Tài Sản & Drawdown",
  tabPortfolioNotes: "Ghi Chú Phân Tích",
  tabDataRefreshLog: "Nhật Ký Cập Nhật",

  // Watchlist & Notes
  addTicker: "Thêm Mã",
  remove: "Xóa",
  saveNotesBtn: "Lưu Ghi Chú",
  notesAutosaved: "Ghi chú đã tự động lưu",

  // Backtest & Equity
  cagr: "CAGR (%)",
  maxDrawdown: "Max Drawdown (%)",
  sharpe: "Tỷ số Sharpe",
  sortino: "Tỷ số Sortino",
  winRate: "Tỷ lệ Thắng (%)",
  profitFactor: "Profit Factor",

  // States
  loading: "Đang tải dữ liệu...",
  emptyData: "Không có dữ liệu hiển thị",
  errorOccurred: "Đã xảy ra lỗi khi tải dữ liệu",
  retryBtn: "Thử lại",
  staleWarning: "Dữ liệu có thể chưa được cập nhật phiên mới nhất"
};
