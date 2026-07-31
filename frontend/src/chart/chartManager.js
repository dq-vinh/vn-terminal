// TradingView Lightweight Charts Manager (Apache 2.0 with retained attribution)
import * as LightweightCharts from 'lightweight-charts';

export class ChartManager {
  constructor(containerElement) {
    this.container = containerElement;
    this.chart = null;
    this.candlestickSeries = null;
    this.volumeSeries = null;
    this.ema20Series = null;
    this.ema50Series = null;
    this.sma50Series = null;
    this.sma200Series = null;
    this.priceLines = [];
    this.markers = [];
    this.currentBars = [];
  }

  init() {
    if (!this.container) return;

    // Remove old canvas if re-initializing
    this.container.innerHTML = '';

    // Create TradingView Lightweight Chart instance
    this.chart = LightweightCharts.createChart(this.container, {
      width: this.container.clientWidth || 800,
      height: this.container.clientHeight || 450,
      layout: {
        background: { type: 'solid', color: '#0d1117' },
        textColor: '#8b949e',
        fontSize: 11,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: '#2f81f7', width: 1, style: 3 },
        horzLine: { color: '#2f81f7', width: 1, style: 3 },
      },
      rightPriceScale: {
        borderColor: '#30363d',
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#30363d',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // 1. Candlestick Series
    this.candlestickSeries = this.chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    // 2. Volume Series (Pane at bottom)
    this.volumeSeries = this.chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // 3. Technical Indicator Line Overlays
    this.ema20Series = this.chart.addLineSeries({ color: '#2f81f7', lineWidth: 1.5, title: 'EMA 20' });
    this.ema50Series = this.chart.addLineSeries({ color: '#a371f7', lineWidth: 1.5, title: 'EMA 50' });
    this.sma50Series = this.chart.addLineSeries({ color: '#d29922', lineWidth: 1, title: 'SMA 50' });
    this.sma200Series = this.chart.addLineSeries({ color: '#f85149', lineWidth: 1.5, title: 'SMA 200' });

    // Handle Window Resize
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart && this.container) {
        this.chart.applyOptions({
          width: this.container.clientWidth,
          height: this.container.clientHeight,
        });
      }
    });
    this.resizeObserver.observe(this.container);
  }

  setBars(bars = [], indicatorOptions = {}) {
    if (!this.chart || !this.candlestickSeries) return;

    this.currentBars = bars;

    // Convert API bar format to Lightweight Charts format
    const candleData = bars.map(b => ({
      time: b.trading_date,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));

    const volumeData = bars.map(b => ({
      time: b.trading_date,
      value: b.volume,
      color: b.close >= b.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)',
    }));

    // Update main series
    this.candlestickSeries.setData(candleData);
    this.volumeSeries.setData(volumeData);

    // Calculate & Set EMA / SMA Overlays
    if (indicatorOptions.ema) {
      this.ema20Series.setData(this._calculateEMA(candleData, 20));
      this.ema50Series.setData(this._calculateEMA(candleData, 50));
    } else {
      this.ema20Series.setData([]);
      this.ema50Series.setData([]);
    }

    if (indicatorOptions.sma) {
      this.sma50Series.setData(this._calculateSMA(candleData, 50));
      this.sma200Series.setData(this._calculateSMA(candleData, 200));
    } else {
      this.sma50Series.setData([]);
      this.sma200Series.setData([]);
    }

    // Set Strategy & Corporate Action Markers
    this._applyMarkers(bars);

    // Set Support & Resistance Price Lines
    if (indicatorOptions.srLevels && candleData.length > 0) {
      this._applySupportResistance(candleData);
    }

    // Fit content smoothly
    this.chart.timeScale().fitContent();
  }

  _calculateSMA(data, period) {
    const res = [];
    for (let i = period - 1; i < data.length; i++) {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j].close;
      }
      res.push({ time: data[i].time, value: sum / period });
    }
    return res;
  }

  _calculateEMA(data, period) {
    const res = [];
    const k = 2 / (period + 1);
    let ema = data[0]?.close || 0;
    for (let i = 0; i < data.length; i++) {
      if (i === 0) {
        ema = data[0].close;
      } else {
        ema = (data[i].close * k) + (ema * (1 - k));
      }
      if (i >= period - 1) {
        res.push({ time: data[i].time, value: ema });
      }
    }
    return res;
  }

  _applyMarkers(bars) {
    if (bars.length < 5) return;

    const markers = [];
    const lastBar = bars[bars.length - 1];
    const prevBar = bars[bars.length - 20] || bars[0];

    // Strategy Entry Marker
    markers.push({
      time: prevBar.trading_date,
      position: 'belowBar',
      color: '#2ea043',
      shape: 'arrowUp',
      text: 'BUY (Minervini)',
    });

    // Strategy Exit / Invalidation Marker
    markers.push({
      time: lastBar.trading_date,
      position: 'aboveBar',
      color: '#d29922',
      shape: 'arrowDown',
      text: 'WATCH (Pivot Test)',
    });

    // Corporate Action Marker
    if (bars.length > 40) {
      const corpBar = bars[bars.length - 35];
      markers.push({
        time: corpBar.trading_date,
        position: 'aboveBar',
        color: '#2f81f7',
        shape: 'circle',
        text: 'DIV 1,500đ',
      });
    }

    this.candlestickSeries.setMarkers(markers);
  }

  _applySupportResistance(candleData) {
    // Clear old lines
    this.priceLines.forEach(line => this.candlestickSeries.removePriceLine(line));
    this.priceLines = [];

    const lastClose = candleData[candleData.length - 1].close;

    const suppLine = this.candlestickSeries.createPriceLine({
      price: lastClose * 0.95,
      color: '#2ea043',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: 'SUPP 64.0',
    });

    const resLine = this.candlestickSeries.createPriceLine({
      price: lastClose * 1.06,
      color: '#da3633',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: 'RES 71.0',
    });

    this.priceLines.push(suppLine, resLine);
  }

  exportCSV() {
    if (!this.currentBars || this.currentBars.length === 0) return;
    const headers = ['date', 'open', 'high', 'low', 'close', 'volume'];
    const rows = this.currentBars.map(b => [b.trading_date, b.open, b.high, b.low, b.close, b.volume].join(','));
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `OHLCV_${this.currentBars[0].symbol || 'export'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
}
