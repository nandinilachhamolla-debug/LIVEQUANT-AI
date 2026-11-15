
import { useMemo, useState } from 'react'
import { Activity, ShieldCheck, TrendingUp, Wallet } from 'lucide-react'
import './PortfolioLab.css'

const INITIAL_CAPITAL = 300000
const PROFILES = {
  Low: { exposure: 0.30, description: 'Conservative exposure' },
  Medium: { exposure: 0.60, description: 'Balanced exposure' },
  High: { exposure: 0.90, description: 'Higher exposure' },
}

const STRATEGIES = [
  { id: 'buyhold', name: 'Buy & Hold' },
  { id: 'sma', name: 'Moving Average Crossover' },
  { id: 'momentum', name: 'Momentum Strategy' },
]

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function getSignal(prices) {
  if (prices.length < 12) {
    return {
      label: 'INSUFFICIENT DATA',
      explanation: 'At least 12 observations are needed for this baseline signal.',
    }
  }

  const shortAverage = average(prices.slice(-5))
  const longAverage = average(prices.slice(-12))
  const latest = prices[prices.length - 1]

  if (latest > shortAverage && shortAverage > longAverage) {
    return {
      label: 'BULLISH',
      explanation: 'Latest price is above both averages, with the short average above the long average.',
    }
  }

  if (latest < shortAverage && shortAverage < longAverage) {
    return {
      label: 'BEARISH',
      explanation: 'Latest price is below both averages, with the short average below the long average.',
    }
  }

  return {
    label: 'NEUTRAL',
    explanation: 'The moving averages do not show a clear directional alignment.',
  }
}

function backtest(prices, strategy, exposure) {
  if (prices.length < 20) return null

  let cash = INITIAL_CAPITAL
  let units = 0
  let peak = INITIAL_CAPITAL
  let maxDrawdown = 0
  let trades = 0
  const feeRate = 0.0005

  for (let i = 12; i < prices.length; i += 1) {
    const current = prices[i]
    const previous = prices[i - 1]
    let shouldHold = false

    if (strategy === 'buyhold') {
      shouldHold = true
    } else if (strategy === 'sma') {
      const shortNow = average(prices.slice(i - 5, i))
      const longNow = average(prices.slice(i - 12, i))
      shouldHold = shortNow > longNow
    } else if (strategy === 'momentum') {
      shouldHold = current > prices[i - 5]
    }

    const equityBefore = cash + units * current
    const targetUnits = shouldHold
      ? (equityBefore * exposure) / current
      : 0

    const change = targetUnits - units

    if (Math.abs(change * current) > 1) {
      const value = change * current
      const fee = Math.abs(value) * feeRate
      cash -= value + fee
      units = targetUnits
      trades += 1
    }

    const equity = cash + units * current
    peak = Math.max(peak, equity)

    const drawdown = peak > 0 ? ((peak - equity) / peak) * 100 : 0
    maxDrawdown = Math.max(maxDrawdown, drawdown)

    if (!Number.isFinite(previous)) return null
  }

  const finalValue = cash + units * prices[prices.length - 1]
  const profitLoss = finalValue - INITIAL_CAPITAL

  return {
    finalValue,
    profitLoss,
    returnPct: (profitLoss / INITIAL_CAPITAL) * 100,
    maxDrawdown,
    trades,
  }
}

function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

function PortfolioLab({ prices = [], market = 'unknown' }) {
  const [profile, setProfile] = useState('Medium')
  const [strategy, setStrategy] = useState('sma')
  const [scenarioReturn, setScenarioReturn] = useState('3.33')

  const validPrices = useMemo(
    () => prices.map(Number).filter(value => Number.isFinite(value) && value > 0),
    [prices]
  )

  const signal = useMemo(() => getSignal(validPrices), [validPrices])

  const results = useMemo(() => {
    const exposure = PROFILES[profile].exposure

    return STRATEGIES.map(item => ({
      ...item,
      result: backtest(validPrices, item.id, exposure),
    }))
  }, [validPrices, profile])

  const selectedResult = results.find(item => item.id === strategy)?.result
  const scenarioValue = INITIAL_CAPITAL * (1 + (Number(scenarioReturn) || 0) / 100)

  return (
    <section className="portfolio-lab" id="portfolio-lab">
      <div className="pl-heading">
        <div>
          <p className="pl-eyebrow">LIVEQUANT AI · OBJECTIVES 1–3</p>
          <h2>Portfolio & Strategy Lab</h2>
          <p className="pl-subtitle">
            Explore market signals, compare strategies and test virtual portfolio risk.
          </p>
        </div>
        <div className="pl-icon"><Activity size={23} /></div>
      </div>

      <div className="pl-notice">
        <ShieldCheck size={18} />
        <span>
          Educational paper-trading prototype. No real orders, investment advice
          or guaranteed returns.
        </span>
      </div>

      <div className="pl-grid">
        <article className="pl-card">
          <div className="pl-card-title">
            <Activity size={18} />
            <h3>1. Market trend signal</h3>
          </div>
          <div className={`pl-signal ${signal.label.toLowerCase().replaceAll(' ', '-')}`}>
            {signal.label}
          </div>
          <p className="pl-description">{signal.explanation}</p>
          <div className="pl-meta">
            Observations available: <strong>{validPrices.length}</strong>
          </div>
          <p className="pl-footnote">
            Transparent moving-average baseline; not a trained or validated
            predictive AI model.
          </p>
        </article>

        <article className="pl-card">
          <div className="pl-card-title">
            <Wallet size={18} />
            <h3>2. Virtual portfolio</h3>
          </div>
          <label className="pl-label" htmlFor="risk-profile">Risk profile</label>
          <select
            id="risk-profile"
            className="pl-select"
            value={profile}
            onChange={event => setProfile(event.target.value)}
          >
            {Object.keys(PROFILES).map(name => (
              <option key={name} value={name}>{name} Risk</option>
            ))}
          </select>

          <div className="pl-capital">{money(INITIAL_CAPITAL)}</div>
          <p className="pl-description">Starting virtual capital</p>

          <div className="pl-meta">
            Prototype exposure limit: <strong>{PROFILES[profile].exposure * 100}%</strong>
          </div>
          <p className="pl-footnote">
            {PROFILES[profile].description}. These are configurable demo settings,
            not validated risk recommendations.
          </p>
        </article>
      </div>

      <article className="pl-card pl-strategy-card">
        <div className="pl-card-title">
          <TrendingUp size={18} />
          <h3>3. Strategy comparison</h3>
        </div>
        <p className="pl-description">
          Compare simple strategies on the currently available observation sample.
          A minimum of 20 valid prices is required.
        </p>

        <div className="pl-strategy-list">
          {results.map(item => (
            <button
              type="button"
              key={item.id}
              className={`pl-strategy-option ${strategy === item.id ? 'selected' : ''}`}
              onClick={() => setStrategy(item.id)}
            >
              {item.name}
            </button>
          ))}
        </div>

        {selectedResult ? (
          <div className="pl-results">
            <div className="pl-result-main">
              <span>Simulated ending value</span>
              <strong>{money(selectedResult.finalValue)}</strong>
            </div>
            <div className="pl-result-grid">
              <div>
                <span>Profit / Loss</span>
                <strong>{money(selectedResult.profitLoss)}</strong>
              </div>
              <div>
                <span>Return</span>
                <strong>{selectedResult.returnPct.toFixed(2)}%</strong>
              </div>
              <div>
                <span>Maximum drawdown</span>
                <strong>{selectedResult.maxDrawdown.toFixed(2)}%</strong>
              </div>
              <div>
                <span>Position changes</span>
                <strong>{selectedResult.trades}</strong>
              </div>
            </div>
            <p className="pl-footnote">
              Historical sample simulation only. Results exclude taxes and slippage;
              a small illustrative transaction fee is included. Past sample results
              do not predict future performance.
            </p>
          </div>
        ) : (
          <div className="pl-empty">
            <strong>Backtest waiting for data</strong>
            <span>
              At least 20 valid price observations are needed. Current count: {validPrices.length}.
            </span>
          </div>
        )}
      </article>

      <article className="pl-card pl-scenario-card">
        <div className="pl-card-title">
          <Wallet size={18} />
          <h3>Faculty example · Return scenario calculator</h3>
        </div>
        <p className="pl-description">
          Enter a hypothetical percentage change to see how virtual capital would
          change. This is a calculator, not a forecast.
        </p>
        <label className="pl-label" htmlFor="scenario-return">
          Hypothetical return (%)
        </label>
        <input
          id="scenario-return"
          className="pl-input"
          type="number"
          step="0.01"
          value={scenarioReturn}
          onChange={event => setScenarioReturn(event.target.value)}
        />
        <div className="pl-scenario-output">
          <div>
            <span>Starting capital</span>
            <strong>{money(INITIAL_CAPITAL)}</strong>
          </div>
          <div>
            <span>Illustrative ending value</span>
            <strong>{money(scenarioValue)}</strong>
          </div>
          <div>
            <span>Illustrative change</span>
            <strong>{money(scenarioValue - INITIAL_CAPITAL)}</strong>
          </div>
        </div>
        <p className="pl-footnote">
          Example: a hypothetical 3.33% change takes ₹3,00,000 to approximately
          ₹3,09,990 before costs. Actual results can be positive or negative.
        </p>
      </article>

      <p className="pl-data-note">
        Current observation source: <strong>{market}</strong>. These observations
        are not verified historical Indian equity data. Indian stock-market
        backtesting requires a connected and validated NSE/BSE data source.
      </p>
    </section>
  )
}

export default PortfolioLab
