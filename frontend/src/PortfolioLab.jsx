
import { useMemo, useState } from 'react'
import {
  Activity,
  ShieldCheck,
  TrendingUp,
  Wallet,
  AlertTriangle
} from 'lucide-react'
import './PortfolioLab.css'

export default function PortfolioLab({
  prices = [],
  market = 'unknown'
}) {
  const [risk, setRisk] = useState('Medium')
  const [investment, setInvestment] = useState(300000)
  const [expectedReturn, setExpectedReturn] = useState(3.33)

  const riskSettings = {
    Low: {
      exposure: '30%',
      description: 'Lower simulated exposure'
    },
    Medium: {
      exposure: '60%',
      description: 'Balanced simulated exposure'
    },
    High: {
      exposure: '90%',
      description: 'Higher simulated exposure'
    }
  }

  const validPrices = useMemo(
    () =>
      prices
        .map(Number)
        .filter(price => Number.isFinite(price) && price > 0),
    [prices]
  )

  const averagePrice = useMemo(() => {
    if (!validPrices.length) return 0

    return validPrices.reduce((sum, price) => sum + price, 0) /
      validPrices.length
  }, [validPrices])

  const latestPrice = validPrices.length
    ? validPrices[validPrices.length - 1]
    : 0

  const signal = validPrices.length < 20
    ? 'Insufficient data'
    : latestPrice > averagePrice
      ? 'Above average'
      : 'Below average'

  const projectedValue =
    investment * (1 + expectedReturn / 100)

  const hypotheticalGain = projectedValue - investment

  return (
    <section className="portfolio-lab" id="portfolio-lab">
      <div className="lab-heading">
        <div>
          <span className="lab-eyebrow">
            VIRTUAL TRADING ENVIRONMENT
          </span>
          <h2>Portfolio Lab</h2>
          <p>
            Explore hypothetical strategies without using real money.
          </p>
        </div>

        <Activity size={30} />
      </div>

      <div className="lab-grid">
        <article className="lab-card">
          <Wallet size={25} />
          <h3>Virtual Portfolio</h3>
          <p className="lab-value">
            ₹{investment.toLocaleString('en-IN')}
          </p>
          <span>Illustrative starting capital</span>
        </article>

        <article className="lab-card">
          <ShieldCheck size={25} />
          <h3>Risk Profile</h3>

          <select
            value={risk}
            onChange={event => setRisk(event.target.value)}
          >
            <option value="Low">Low Risk</option>
            <option value="Medium">Medium Risk</option>
            <option value="High">High Risk</option>
          </select>

          <p className="lab-value">
            {riskSettings[risk].exposure}
          </p>
          <span>{riskSettings[risk].description}</span>
        </article>

        <article className="lab-card">
          <TrendingUp size={25} />
          <h3>Market Signal</h3>
          <p className="lab-value">{signal}</p>
          <span>
            Based on a simple average of available prices
          </span>
        </article>

        <article className="lab-card">
          <Activity size={25} />
          <h3>Market Data</h3>
          <p className="lab-value">{validPrices.length}</p>
          <span>Valid price observations</span>
        </article>
      </div>

      <div className="lab-panel">
        <h3>Hypothetical Return Calculator</h3>
        <p>
          Change the inputs to explore an illustrative scenario.
          This is not a prediction.
        </p>

        <label htmlFor="investment">
          Virtual starting amount (₹)
        </label>

        <input
          id="investment"
          type="number"
          min="1000"
          max="10000000"
          step="1000"
          value={investment}
          onChange={event =>
            setInvestment(Math.max(0, Number(event.target.value)))
          }
        />

        <label htmlFor="return">
          Hypothetical return: {expectedReturn.toFixed(2)}%
        </label>

        <input
          id="return"
          type="range"
          min="-20"
          max="20"
          step="0.01"
          value={expectedReturn}
          onChange={event =>
            setExpectedReturn(Number(event.target.value))
          }
        />

        <div className="lab-result">
          <div>
            <span>Illustrative final value</span>
            <strong>
              ₹{projectedValue.toLocaleString('en-IN', {
                maximumFractionDigits: 2
              })}
            </strong>
          </div>

          <div>
            <span>Illustrative change</span>
            <strong>
              ₹{hypotheticalGain.toLocaleString('en-IN', {
                maximumFractionDigits: 2
              })}
            </strong>
          </div>
        </div>
      </div>

      <div className="lab-panel">
        <h3>Data Analysis Summary</h3>

        <p>
          Selected market: <strong>{market}</strong>
        </p>

        <p>
          Latest available price:{' '}
          <strong>
            {latestPrice
              ? latestPrice.toLocaleString('en-IN')
              : 'Not available'}
          </strong>
        </p>

        <p>
          Average available price:{' '}
          <strong>
            {averagePrice
              ? averagePrice.toLocaleString('en-IN', {
                  maximumFractionDigits: 2
                })
              : 'Not available'}
          </strong>
        </p>

        {validPrices.length < 20 && (
          <div className="lab-warning">
            <AlertTriangle size={18} />
            More market observations are needed for a meaningful
            moving-average analysis.
          </div>
        )}
      </div>

      <p className="lab-disclaimer">
        Educational simulation only. Returns and risk profiles are
        hypothetical, not guaranteed, and do not represent actual
        trading performance or investment advice.
      </p>
    </section>
  )
}