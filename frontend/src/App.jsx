
import React, {
  useCallback,
  useEffect,
  useMemo,
  useState
} from 'react'

import axios from 'axios'

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  Gauge,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Wifi,
  X
} from 'lucide-react'

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

import PortfolioLab from './PortfolioLab'
import './App.css'

// --------------------------------------------------
// API CONFIGURATION
// --------------------------------------------------

const API_BASE_URL = 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000
})

// --------------------------------------------------
// HELPER FUNCTIONS
// --------------------------------------------------

function getValue(object, keys, fallback = null) {
  if (!object) return fallback

  for (const key of keys) {
    const value = object[key]

    if (value !== undefined && value !== null) {
      return value
    }
  }

  return fallback
}

function getArray(object, keys) {
  const value = getValue(object, keys, [])

  return Array.isArray(value) ? value : []
}

function formatPrice(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) return '--'

  return number.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatNumber(value, digits = 2) {
  const number = Number(value)

  if (!Number.isFinite(number)) return '--'

  return number.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits
  })
}

function formatTime(value) {
  if (!value) return '--'

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// Normalize actual /api/ticks/{market} response:
// { market, count, observations: [...] }

function normalizeChartData(response) {
  const observations = getArray(response, [
    'observations',
    'ticks',
    'data',
    'items'
  ])

  return observations
    .map((item, index) => {
      const price = Number(
        getValue(item, [
          'price',
          'last_price',
          'close'
        ])
      )

      const time = getValue(item, [
        'received_at',
        'timestamp',
        'provider_timestamp',
        'time',
        'created_at'
      ])

      return {
        index,
        time: formatTime(time),
        price,
        rawTime: time
      }
    })
    .filter(item => Number.isFinite(item.price))
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  status
}) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{label}</span>

        <span className="metric-icon">
          <Icon size={18} />
        </span>
      </div>

      <div className="metric-value">{value}</div>

      <div className="metric-detail">
        <span className={status || ''}>{detail}</span>
      </div>
    </div>
  )
}

// --------------------------------------------------
// MAIN APPLICATION
// --------------------------------------------------

function App() {
  const [health, setHealth] = useState(null)
  const [marketInfo, setMarketInfo] = useState(null)

  const [selectedMarket, setSelectedMarket] = useState('crypto')

  const [latest, setLatest] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [chartData, setChartData] = useState([])

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [mobileMenu, setMobileMenu] = useState(false)

  // NSE historical dataset + experimental next-session model
  const [equityStatus, setEquityStatus] = useState(null)
  const [equitySymbols, setEquitySymbols] = useState([])
  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE')
  const [symbolInput, setSymbolInput] = useState('RELIANCE')
  const [equityPrediction, setEquityPrediction] = useState(null)
  const [equityHistory, setEquityHistory] = useState([])
  const [equityLoading, setEquityLoading] = useState(false)
  const [equityError, setEquityError] = useState('')

  // ------------------------------------------------
  // LOAD BACKEND OVERVIEW
  // ------------------------------------------------

  const loadOverview = useCallback(async () => {
    try {
      const [healthRes, marketsRes] = await Promise.all([
        api.get('/api/health'),
        api.get('/api/markets')
      ])

      setHealth(healthRes.data)

      const marketList = getArray(marketsRes.data, [
        'markets'
      ])

      const cryptoMarket = marketList.find(
        item => item.id === 'crypto'
      )

      setMarketInfo(cryptoMarket || null)

      if (cryptoMarket?.status === 'CONNECTED') {
        setSelectedMarket('crypto')
      }

      setError('')
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        'Cannot connect to the backend. Check whether FastAPI is running on port 8000.'
      )
    }
  }, [])

  // ------------------------------------------------
  // LOAD MARKET DATA
  // ------------------------------------------------

  const loadMarketData = useCallback(async () => {
    if (!selectedMarket) return

    setRefreshing(true)

    try {
      const market = encodeURIComponent(selectedMarket)

      const results = await Promise.allSettled([
        api.get(`/api/latest/${market}`),
        api.get(`/api/analytics/${market}`),
        api.get(`/api/alerts/${market}`),
        api.get(`/api/ticks/${market}`)
      ])

      let latestWorked = false
      let analyticsWorked = false

      // Latest market observation
      if (results[0].status === 'fulfilled') {
        setLatest(results[0].value.data)
        latestWorked = true
      }

      // Statistical and ML analytics
      if (results[1].status === 'fulfilled') {
        setAnalytics(results[1].value.data)
        analyticsWorked = true
      }

      // Backend alert list
      if (results[2].status === 'fulfilled') {
        setAlerts(
          getArray(results[2].value.data, [
            'alerts',
            'data',
            'items'
          ])
        )
      }

      // Historical market observations
      if (results[3].status === 'fulfilled') {
        setChartData(
          normalizeChartData(results[3].value.data)
        )
      }

      if (!latestWorked && !analyticsWorked) {
        setError(
          'Latest market data and analytics endpoints are unavailable.'
        )
      } else {
        setError('')
        setLastUpdated(new Date())
      }

    } catch (err) {
      console.error('Market data error:', err)
      setError('Unable to load market data.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [selectedMarket])

  // ------------------------------------------------
  // LOAD NSE HISTORICAL DATA AND EXPERIMENTAL MODEL
  // ------------------------------------------------

  const loadEquity = useCallback(async (requestedSymbol = selectedSymbol) => {
    const cleanSymbol = String(requestedSymbol || '').trim().toUpperCase()
    if (!cleanSymbol) return

    setEquityLoading(true)
    setEquityError('')

    try {
      const [statusRes, predictionRes, historyRes] = await Promise.all([
        api.get('/api/equity/status'),
        api.get(`/api/equity/predict/${encodeURIComponent(cleanSymbol)}`),
        api.get(`/api/equity/history/${encodeURIComponent(cleanSymbol)}?limit=60`)
      ])

      setEquityStatus(statusRes.data)
      setEquityPrediction(predictionRes.data)
      setEquityHistory(getArray(historyRes.data, ['history']))
      setSelectedSymbol(cleanSymbol)
      setSymbolInput(cleanSymbol)
    } catch (err) {
      setEquityError(
        err.response?.data?.detail ||
        `Could not load ${cleanSymbol}. Check the symbol and NSE API.`
      )
      setEquityPrediction(null)
      setEquityHistory([])
    } finally {
      setEquityLoading(false)
    }
  }, [selectedSymbol])

  useEffect(() => {
    let active = true

    Promise.all([
      api.get('/api/equity/status'),
      api.get('/api/equity/symbols')
    ]).then(([statusRes, symbolsRes]) => {
      if (!active) return
      setEquityStatus(statusRes.data)
      setEquitySymbols(getArray(symbolsRes.data, ['symbols']))
    }).catch(err => {
      if (active) setEquityError(
        err.response?.data?.detail || 'NSE historical API is unavailable.'
      )
    })

    return () => { active = false }
  }, [])

  useEffect(() => {
    loadEquity('RELIANCE')
  }, [])

  // ------------------------------------------------
  // INITIAL LOAD
  // ------------------------------------------------

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  // ------------------------------------------------
  // AUTOMATIC DATA REFRESH
  // ------------------------------------------------

  useEffect(() => {
    loadMarketData()

    const interval = setInterval(() => {
      loadMarketData()
    }, 5000)

    return () => clearInterval(interval)
  }, [loadMarketData])

  // ------------------------------------------------
  // EXTRACT ACTUAL BACKEND RESPONSE STRUCTURES
  // ------------------------------------------------

  const observation = latest?.observation || latest

  const currentPrice = getValue(observation, [
    'price',
    'last_price',
    'close'
  ])

  const bid = getValue(observation, [
    'bid',
    'best_bid'
  ])

  const ask = getValue(observation, [
    'ask',
    'best_ask'
  ])

  const volume = getValue(observation, [
    'volume_24h',
    'volume'
  ])

  const symbol = getValue(
    observation,
    ['symbol'],
    'BTCUSDT'
  )

  // Actual analytics response:
  // { analysis: { price_analysis, volatility,
  // statistical_analysis, machine_learning, ... } }

  const analysis = analytics?.analysis || analytics || {}

  const priceAnalysis = analysis.price_analysis || {}
  const volatilityData = analysis.volatility || {}
  const statistical = analysis.statistical_analysis || {}
  const machineLearning = analysis.machine_learning || {}
  const liquidity = analysis.liquidity_analysis || {}

  const zScore = getValue(statistical, [
    'z_score'
  ])

  const volatility = getValue(volatilityData, [
    'return_standard_deviation_pct'
  ])

  const statisticalAnomaly = getValue(statistical, [
    'anomaly_detected'
  ])

  const mlAnomaly = getValue(machineLearning, [
    'anomaly_detected'
  ])

  const decisionScore = getValue(machineLearning, [
    'decision_score'
  ])

  const analyticsStatus = getValue(
    analysis,
    ['status'],
    'WAITING FOR DATA'
  )

  const backendAlert = getValue(analysis, [
    'alert'
  ])

  // IMPORTANT FIX:
  // /api/health does not provide crypto_status.
  // /api/markets provides markets[].status.

  const dataStatus = marketInfo?.status || 'CHECKING'

  const isConnected = dataStatus === 'CONNECTED'

  const chartDirection = chartData.length >= 2
    ? chartData[chartData.length - 1].price >=
      chartData[0].price
    : null

  // ------------------------------------------------
  // DISPLAY ALERTS
  // ------------------------------------------------

  const displayedAlerts = useMemo(() => {
    if (alerts.length > 0) {
      return alerts
    }

    if (
      backendAlert &&
      backendAlert !== 'NONE' &&
      backendAlert !== 'NO_ALERT' &&
      backendAlert !== 'NORMAL_PATTERN'
    ) {
      return [{
        id: 'analytics-alert',
        title: backendAlert,
        explanation:
          analysis.explanation ||
          'Analytics engine reported unusual activity.',
        timestamp: analytics?.generated_at
      }]
    }

    return []
  }, [
    alerts,
    backendAlert,
    analysis.explanation,
    analytics?.generated_at
  ])

  // ------------------------------------------------
  // MANUAL REFRESH
  // ------------------------------------------------

  const refreshAll = async () => {
    await loadOverview()
    await loadMarketData()
  }

  // ------------------------------------------------
  // DASHBOARD UI
  // ------------------------------------------------

  return (
    <div className="app-shell">

      {/* SIDEBAR */}

      <aside className={`sidebar ${
        mobileMenu ? 'sidebar-open' : ''
      }`}>

        <div className="brand">

          <div className="brand-mark">
            <Activity size={25} />
          </div>

          <div>
            <h2>
              LIVEQUANT<span> AI</span>
            </h2>

            <p>QUANTITATIVE INTELLIGENCE</p>
          </div>

          <button
            className="mobile-close"
            onClick={() => setMobileMenu(false)}
          >
            <X size={20} />
          </button>

        </div>

        <div className="sidebar-label">
          WORKSPACE
        </div>

        <nav className="navigation">

          <a
            className="nav-item active"
            href="#overview"
          >
            <LayoutDashboard size={19} />
            Overview
          </a>

          <a
            className="nav-item"
            href="#portfolio-lab"
          >
            <Activity size={19} />
            Portfolio Lab
          </a>

          <a
            className="nav-item"
            href="#market"
          >
            <TrendingUp size={19} />
            Market Monitor
          </a>

          <a
            className="nav-item"
            href="#analytics"
          >
            <BrainCircuit size={19} />
            AI Analytics
          </a>

          <a
            className="nav-item"
            href="#alerts"
          >
            <Bell size={19} />
            Alerts

            <span className="nav-count">
              {displayedAlerts.length}
            </span>
          </a>

        </nav>

        <div className="sidebar-label">
          SYSTEM
        </div>

        <div className="system-info">

          <div className="system-icon">
            <Database size={18} />
          </div>

          <div>
            <strong>Market Data Engine</strong>
            <span>{dataStatus}</span>
          </div>

        </div>

        <div className="sidebar-bottom">

          <div className="security-icon">
            <ShieldCheck size={18} />
          </div>

          <div>
            <strong>Research Mode</strong>
            <span>Decision support only</span>
          </div>

        </div>

      </aside>

      {/* MAIN CONTENT */}

      <main className="main-content">

        {/* TOPBAR */}

        <header className="topbar">

          <div className="topbar-left">

            <button
              className="mobile-menu"
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={21} />
            </button>

            <div>
              <p className="breadcrumb">
                WORKSPACE / OVERVIEW
              </p>

              <h1>Market Intelligence</h1>
            </div>

          </div>

          <div className="topbar-right">

            <div className="live-indicator">
              <span className="live-dot" />
              {String(dataStatus).toUpperCase()}
            </div>

            <button
              className="refresh-button"
              onClick={refreshAll}
              disabled={refreshing}
            >
              <RefreshCw
                size={16}
                className={refreshing ? 'spinning' : ''}
              />

              <span>Refresh</span>
            </button>

            <div className="profile-avatar">
              LQ
            </div>

          </div>

        </header>

        {/* ERROR MESSAGE */}

        {error && (
          <div className="error-banner">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* WELCOME SECTION */}

        <section
          className="welcome-row"
          id="overview"
        >

          <div>

            <p className="eyebrow">
              QUANTITATIVE MARKET RESEARCH PLATFORM
            </p>

            <h2>Market overview</h2>

            <p className="section-description">
              NSE historical AI research and separate CoinDCX live market observations.
            </p>

          </div>

          <div className="updated-label">
            <Clock3 size={15} />

            Updated: {
              lastUpdated
                ? lastUpdated.toLocaleTimeString()
                : '--'
            }
          </div>

        </section>

        {/* INDIAN STOCK MARKET - PRIORITY PANEL */}

        <section className="equity-section" id="indian-stocks">
          <div className="equity-heading">
            <div>
              <p className="eyebrow">NSE HISTORICAL DATA · MACHINE LEARNING</p>
              <h2>Indian Stock Market AI</h2>
              <p className="section-description">
                Experimental next-session classification using historical NSE end-of-day data.
              </p>
            </div>
            <span className="equity-ready">
              {equityStatus?.dataset_available && equityStatus?.model_available
                ? 'DATASET + MODEL READY'
                : 'CHECKING MODEL'}
            </span>
          </div>

          <div className="equity-controls">
            <label htmlFor="equity-symbol">SEARCH NSE SYMBOL</label>
            <input
              id="equity-symbol"
              list="equity-symbol-list"
              value={symbolInput}
              onChange={event => setSymbolInput(event.target.value.toUpperCase())}
              onKeyDown={event => {
                if (event.key === 'Enter') loadEquity(symbolInput)
              }}
              placeholder="Try RELIANCE, TCS, INFY"
            />
            <datalist id="equity-symbol-list">
              {equitySymbols.map(item => <option key={item} value={item} />)}
            </datalist>
            <button onClick={() => loadEquity(symbolInput)} disabled={equityLoading}>
              {equityLoading ? 'Loading...' : 'Analyze stock'}
            </button>
            <span className="equity-symbol-count">
              {equitySymbols.length.toLocaleString('en-IN')} symbols in dataset
            </span>
          </div>

          {equityError && <div className="equity-error"><AlertTriangle size={16} />{equityError}</div>}

          {equityPrediction && (
            <>
              <div className="equity-summary-grid">
                <div className="equity-price-card">
                  <span>{equityPrediction.symbol} · LATEST HISTORICAL CLOSE</span>
                  <strong>₹{formatPrice(equityPrediction.latest_close)}</strong>
                  <small>Session: {equityPrediction.latest_session}</small>
                </div>
                <div className="equity-prediction-card">
                  <span>EXPERIMENTAL NEXT-SESSION OUTPUT</span>
                  <strong className={`prediction-${String(equityPrediction.prediction).toLowerCase()}`}>
                    {equityPrediction.prediction}
                  </strong>
                  <small>Model: {equityPrediction.model}</small>
                </div>
                <div className="equity-score-card">
                  <span>MODEL SCORES</span>
                  {['UP', 'DOWN', 'SIDEWAYS'].map(label => (
                    <div className="equity-score-row" key={label}>
                      <span>{label}</span>
                      <div className="equity-score-track">
                        <div style={{ width: `${Math.max(0, Math.min(100, Number(equityPrediction.model_scores_percent?.[label] || 0)))}%` }} />
                      </div>
                      <b>{formatNumber(equityPrediction.model_scores_percent?.[label], 2)}%</b>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel equity-chart-panel">
                <div className="panel-header">
                  <div>
                    <h3>{equityPrediction.symbol} historical price</h3>
                    <p>Daily closing prices from the NSE EOD dataset</p>
                  </div>
                  <span className="equity-history-count">{equityHistory.length} sessions</span>
                </div>
                <div className="equity-chart-container">
                  {equityHistory.length > 1 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={equityHistory}>
                        <defs>
                          <linearGradient id="equityPriceGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#65a9ff" stopOpacity={0.28} />
                            <stop offset="95%" stopColor="#65a9ff" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#252b38" strokeDasharray="4 5" vertical={false} />
                        <XAxis dataKey="Date" stroke="#788397" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={28} />
                        <YAxis stroke="#788397" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} domain={['auto', 'auto']} width={75} />
                        <Tooltip contentStyle={{ background: '#171e2a', border: '1px solid #303b4b', borderRadius: '9px', color: '#fff' }} formatter={value => [`₹${formatPrice(value)}`, 'Close']} />
                        <Area type="monotone" dataKey="Close" stroke="#65a9ff" strokeWidth={2} fill="url(#equityPriceGradient)" dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : <div className="empty-chart">No historical chart data available for this symbol.</div>}
                </div>
              </div>
              <p className="equity-warning"><ShieldCheck size={15} />{equityPrediction.warning} Historical EOD data is not a live NSE feed. This research prototype does not execute trades.</p>
            </>
          )}
        </section>

        {/* CRYPTO MARKET - PRESERVED SEPARATELY */}

        <section
          className="market-strip"
          id="market"
        >

          <div className="market-identity">

            <div className="coin-icon">
              ₿
            </div>

            <div>
              <h3>{symbol}</h3>
              <span>CRYPTO MARKET · COINDCX</span>
            </div>

          </div>

          <div className="market-selector">

            <label htmlFor="market-select">
              SELECT MARKET
            </label>

            <select
              id="market-select"
              value={selectedMarket}
              onChange={event =>
                setSelectedMarket(event.target.value)
              }
            >
              <option value="crypto">
                Cryptocurrency · LIVE
              </option>

              <option value="stocks" disabled>
                Indian Stocks · Historical AI panel above
              </option>

            </select>

          </div>

          <div className="market-price">

            <span>LAST OBSERVED PRICE</span>

            <strong>
              {currentPrice !== null
                ? `$${formatPrice(currentPrice)}`
                : '--'}
            </strong>

            <small>
              Source: CoinDCX backend observation
            </small>

          </div>

          <div className="market-meta">

            <div>
              <span>BEST BID</span>

              <strong>
                {bid !== null
                  ? formatPrice(bid)
                  : '--'}
              </strong>
            </div>

            <div>
              <span>BEST ASK</span>

              <strong>
                {ask !== null
                  ? formatPrice(ask)
                  : '--'}
              </strong>
            </div>

            <div>
              <span>24H VOLUME</span>

              <strong>
                {volume !== null
                  ? formatNumber(volume)
                  : '--'}
              </strong>
            </div>

          </div>

        </section>

        {/* METRICS */}

        <section className="metrics-grid">

          <MetricCard
            label="Market Price"
            value={
              currentPrice !== null
                ? `$${formatPrice(currentPrice)}`
                : '--'
            }
            detail="Latest observed value"
            icon={TrendingUp}
          />

          <MetricCard
            label="Volatility"
            value={
              volatility !== null
                ? `${formatNumber(volatility, 5)}%`
                : '--'
            }
            detail="Return standard deviation"
            icon={Activity}
          />

          <MetricCard
            label="Z-Score"
            value={
              zScore !== null
                ? formatNumber(zScore, 3)
                : '--'
            }
            detail="Statistical deviation"
            icon={Gauge}
          />

          <MetricCard
            label="AI Anomaly"
            value={
              mlAnomaly === null
                ? '--'
                : mlAnomaly
                  ? 'Detected'
                  : 'Normal'
            }
            detail="Isolation Forest result"
            icon={BrainCircuit}
            status={
              mlAnomaly === null
                ? ''
                : mlAnomaly
                  ? 'warning-text'
                  : 'success-text'
            }
          />

        </section>

        {/* CHART AND ANALYTICS */}

        <section className="content-grid">

          {/* MARKET CHART */}

          <div className="panel chart-panel">

            <div className="panel-header">

              <div>
                <h3>Market price movement</h3>

                <p>
                  Observed market data from the backend
                </p>
              </div>

              <div className="chart-status">
                <span className="chart-dot" />
                LIVE FEED
              </div>

            </div>

            <div className="chart-summary">

              <div>
                <span>Latest observation</span>

                <strong>
                  {currentPrice !== null
                    ? `$${formatPrice(currentPrice)}`
                    : '--'}
                </strong>
              </div>

              <div className={`direction ${
                chartDirection === null
                  ? ''
                  : chartDirection
                    ? 'positive'
                    : 'negative'
              }`}>

                {chartDirection === null ? (
                  <span>Waiting for observations</span>
                ) : (
                  <>
                    {chartDirection
                      ? <ArrowUpRight size={17} />
                      : <ArrowDownRight size={17} />}

                    <span>
                      {chartDirection
                        ? 'Up from first point'
                        : 'Down from first point'}
                    </span>
                  </>
                )}

              </div>

            </div>

            <div className="chart-container">

              {chartData.length > 1 ? (

                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >

                  <AreaChart data={chartData}>

                    <defs>
                      <linearGradient
                        id="priceGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#32d6a0"
                          stopOpacity={0.25}
                        />

                        <stop
                          offset="95%"
                          stopColor="#32d6a0"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>

                    <CartesianGrid
                      stroke="#252b38"
                      strokeDasharray="4 5"
                      vertical={false}
                    />

                    <XAxis
                      dataKey="time"
                      stroke="#788397"
                      tick={{ fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={30}
                    />

                    <YAxis
                      stroke="#788397"
                      tick={{ fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      domain={['auto', 'auto']}
                      width={75}
                    />

                    <Tooltip
                      contentStyle={{
                        background: '#171e2a',
                        border: '1px solid #303b4b',
                        borderRadius: '9px',
                        color: '#fff'
                      }}
                      formatter={value => [
                        `$${formatPrice(value)}`,
                        'Price'
                      ]}
                    />

                    <Area
                      type="monotone"
                      dataKey="price"
                      stroke="#32d6a0"
                      strokeWidth={2}
                      fill="url(#priceGradient)"
                      connectNulls={false}
                      dot={false}
                    />

                  </AreaChart>

                </ResponsiveContainer>

              ) : (

                <div className="empty-chart">

                  <BarChart3 size={36} />

                  <strong>
                    {loading
                      ? 'Loading market observations...'
                      : 'Waiting for chart history'}
                  </strong>

                  <span>
                    The chart requires historical observations from the ticks endpoint.
                  </span>

                </div>

              )}

            </div>

          </div>

          {/* AI ANALYTICS */}

          <div
            className="panel analytics-panel"
            id="analytics"
          >

            <div className="panel-header">

              <div>
                <h3>AI analytics engine</h3>

                <p>
                  Statistical and machine learning analysis
                </p>
              </div>

              <BrainCircuit
                size={21}
                className="panel-accent"
              />

            </div>

            <div className="analysis-status">

              <span>ANALYSIS STATUS</span>

              <strong>
                {String(analyticsStatus).replaceAll('_', ' ')}
              </strong>

            </div>

            <div className="analysis-row">

              <div className="analysis-icon">
                <Activity size={18} />
              </div>

              <div className="analysis-info">
                <strong>Statistical analysis</strong>
                <span>Z-score and volatility</span>
              </div>

              <span className="analysis-value">
                {zScore !== null
                  ? 'Available'
                  : 'Pending'}
              </span>

            </div>

            <div className="analysis-row">

              <div className="analysis-icon purple">
                <BrainCircuit size={18} />
              </div>

              <div className="analysis-info">
                <strong>Statistical anomaly</strong>
                <span>Z-score based detection</span>
              </div>

              <span className={`analysis-value ${
                statisticalAnomaly === null
                  ? ''
                  : statisticalAnomaly
                    ? 'warning-text'
                    : 'success-text'
              }`}>
                {statisticalAnomaly === null
                  ? 'Pending'
                  : statisticalAnomaly
                    ? 'Detected'
                    : 'Normal'}
              </span>

            </div>

            <div className="analysis-row">

              <div className="analysis-icon purple">
                <BrainCircuit size={18} />
              </div>

              <div className="analysis-info">
                <strong>Isolation Forest</strong>
                <span>Machine learning detection</span>
              </div>

              <span className={`analysis-value ${
                mlAnomaly === null
                  ? ''
                  : mlAnomaly
                    ? 'warning-text'
                    : 'success-text'
              }`}>
                {mlAnomaly === null
                  ? 'Pending'
                  : mlAnomaly
                    ? 'Detected'
                    : 'Normal'}
              </span>

            </div>

            <div className="analysis-row">

              <div className="analysis-icon blue">
                <Gauge size={18} />
              </div>

              <div className="analysis-info">
                <strong>Liquidity metrics</strong>
                <span>Bid and ask observations</span>
              </div>

              <span className="analysis-value">
                {bid !== null && ask !== null
                  ? 'Available'
                  : 'Pending'}
              </span>

            </div>

            <div className="analysis-row">

              <div className="analysis-icon">
                <Activity size={18} />
              </div>

              <div className="analysis-info">
                <strong>ML decision score</strong>
                <span>Isolation Forest output</span>
              </div>

              <span className="analysis-value">
                {decisionScore !== null
                  ? formatNumber(decisionScore, 5)
                  : 'Pending'}
              </span>

            </div>

            <div className="analysis-note">
              <ShieldCheck size={17} />

              <span>
                AI outputs are analytical signals, not guaranteed trading predictions.
              </span>
            </div>

          </div>

        </section>

        {/* ALERTS AND CONNECTIONS */}

        <section className="bottom-grid">

          {/* ALERTS */}

          <div
            className="panel alerts-panel"
            id="alerts"
          >

            <div className="panel-header">

              <div>
                <h3>Market alerts</h3>

                <p>
                  Alerts generated by the backend analytics engine
                </p>
              </div>

              <span className="alert-count">
                {displayedAlerts.length} ALERTS
              </span>

            </div>

            {displayedAlerts.length > 0 ? (

              <div className="alerts-list">

                {displayedAlerts.slice(0, 6).map(
                  (alert, index) => (

                    <div
                      className="alert-item"
                      key={alert.id || index}
                    >

                      <div className="alert-symbol">
                        <AlertTriangle size={17} />
                      </div>

                      <div className="alert-details">

                        <strong>
                          {getValue(
                            alert,
                            ['title', 'type', 'alert_type'],
                            'Market activity alert'
                          )}
                        </strong>

                        <span>
                          {getValue(
                            alert,
                            [
                              'explanation',
                              'message',
                              'description'
                            ],
                            'Backend alert received'
                          )}
                        </span>

                      </div>

                      <span className="alert-time">
                        {formatTime(
                          getValue(alert, [
                            'timestamp',
                            'created_at',
                            'received_at'
                          ])
                        )}
                      </span>

                    </div>

                  )
                )}

              </div>

            ) : (

              <div className="empty-alerts">

                <CheckCircle2 size={24} />

                <strong>
                  No backend alerts received
                </strong>

                <span>
                  Alerts will appear here when generated by the analytics engine.
                </span>

              </div>

            )}

          </div>

          {/* DATA CONNECTIONS */}

          <div className="panel connection-panel">

            <div className="panel-header">

              <div>
                <h3>Data connections</h3>

                <p>Provider integration status</p>
              </div>

              <Wifi
                size={20}
                className="panel-accent"
              />

            </div>

            <div className="connection-item">

              <div className="connection-logo crypto-logo">
                ₿
              </div>

              <div className="connection-info">

                <strong>Crypto market feed</strong>
                <span>CoinDCX public ticker</span>

              </div>

              <span className={`connection-state ${
                isConnected
                  ? 'connected'
                  : 'disconnected'
              }`}>
                {isConnected
                  ? 'CONNECTED'
                  : 'OFFLINE'}
              </span>

            </div>

            <div className="connection-item">

              <div className="connection-logo stock-logo">
                ₹
              </div>

              <div className="connection-info">

                <strong>Indian stock AI dataset</strong>
                <span>NSE historical EOD + Random Forest</span>

              </div>

              <span className={`connection-state ${equityStatus?.dataset_available && equityStatus?.model_available ? 'connected' : 'disconnected'}`}>
                {equityStatus?.dataset_available && equityStatus?.model_available ? 'MODEL READY' : 'UNAVAILABLE'}
              </span>

            </div>

            <div className="connection-footer">

              <Database size={15} />

              <span>
                Historical NSE analysis is available; an authorized live NSE feed is not configured.
              </span>

            </div>

            {marketInfo && (

              <div className="connection-footer">

                <Clock3 size={15} />

                <span>
                  Crypto polling interval: {
                    marketInfo.poll_interval_seconds ?? 5
                  } seconds
                </span>

              </div>

            )}

          </div>

        </section>

        {/* PORTFOLIO LAB */}

        <section id="portfolio-lab">
          <PortfolioLab
            prices={chartData.map(point => point.price)}
            market={selectedMarket}
          />
        </section>

        {/* FOOTER */}

        <footer className="footer">

          <div>
            LIVEQUANT AI <span>·</span> Quantitative Market Intelligence
          </div>

          <div>
            Research prototype · Virtual portfolio only · No live order execution
          </div>

        </footer>

      </main>

    </div>
  )
}

export default App