// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: chart-line;

/*
 * Finance Board - iOS Scriptable Widget
 * Displays Total Asset Value and PnL metrics from your personal finance dashboard.
 */

// ==========================================
// User Configuration
// ==========================================
// IMPORTANT: iOS widgets cannot connect to 'localhost' or '127.0.0.1' because they run on your iPhone, not your Mac.
// If testing locally, map this to your Mac's IPv4 Address on the local Wi-Fi, e.g., "http://192.168.x.x:8000"
// Ensure both your iPhone and Mac are on the same Wi-Fi network.
const BACKEND_URL = "http://192.168.1.100:8000"

// ==========================================

async function fetchPositions() {
  const url = `${BACKEND_URL}/api/positions`
  const req = new Request(url)
  req.timeoutInterval = 10 // 10 seconds timeout
  try {
    const rawPositions = await req.loadJSON()
    return rawPositions
  } catch (err) {
    console.error("Failed to fetch positions: " + err)
    return null
  }
}

function calculateMetrics(positions) {
  let totalValue = 0
  let totalCost = 0
  let unrealizedPnL = 0

  // TODO [Future Expansion Interface]: Add daily_pnl calculation here when the backend provides it.
  // The API could either return `daily_pnl` directly per position, or provide yesterday's closing price.
  // let dailyPnL = 0 

  for (const pos of positions) {
    if (pos.current_value) totalValue += pos.current_value
    if (pos.unrealized_pnl) unrealizedPnL += pos.unrealized_pnl
    if (pos.total_quantity > 0 && pos.average_cost > 0) {
      totalCost += (pos.total_quantity * pos.average_cost)
    }

    // TODO [Future]: if (pos.daily_pnl) dailyPnL += pos.daily_pnl
  }

  let pnlPercent = 0
  if (totalCost > 0) {
    pnlPercent = (unrealizedPnL / totalCost) * 100
  }

  return {
    totalValue,
    unrealizedPnL,
    pnlPercent,
    // dailyPnL // reserved for future
  }
}

function formatCurrency(num) {
  return "¥ " + num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(num) {
  return (num > 0 ? "+" : "") + num.toFixed(2) + "%"
}

async function createWidget(data) {
  const widget = new ListWidget()

  // Theme configuration for Light & Dark mode
  const bgC = Color.dynamic(new Color("#ffffff"), new Color("#1c1c1e"))
  const textC = Color.dynamic(new Color("#000000"), new Color("#ffffff"))
  const subTextC = Color.dynamic(new Color("#666666"), new Color("#aaaaaa"))
  const greenC = Color.dynamic(new Color("#34c759"), new Color("#30d158"))
  const redC = Color.dynamic(new Color("#ff3b30"), new Color("#ff453a"))

  widget.backgroundColor = bgC

  // Title Row
  const titleStack = widget.addStack()
  titleStack.centerAlignContent()
  const icon = titleStack.addText("💰 ")
  icon.font = Font.systemFont(14)
  const titleText = titleStack.addText("Finance Board")
  titleText.font = Font.boldSystemFont(14)
  titleText.textColor = textC
  widget.addSpacer(8)

  if (!data) {
    // Error State UI
    const errText = widget.addText("Failed to load data.")
    errText.textColor = redC
    errText.font = Font.systemFont(12)
    widget.addSpacer(4)
    const subErr = widget.addText("Check BACKEND_URL & Network.")
    subErr.textColor = subTextC
    subErr.font = Font.systemFont(10)
    return widget
  }

  const metrics = calculateMetrics(data)

  // Total Value Label
  const valueLabel = widget.addText("Total Value")
  valueLabel.font = Font.systemFont(12)
  valueLabel.textColor = subTextC

  // Total Value Number
  const totalValueText = widget.addText(formatCurrency(metrics.totalValue))
  totalValueText.font = Font.boldSystemFont(22)
  totalValueText.textColor = textC

  widget.addSpacer(4)

  // PnL Label
  const pnlText = widget.addText("Tot PnL: " + formatCurrency(metrics.unrealizedPnL) + " (" + formatPercent(metrics.pnlPercent) + ")")
  pnlText.font = Font.systemFont(14)

  if (metrics.unrealizedPnL > 0) {
    pnlText.textColor = greenC
  } else if (metrics.unrealizedPnL < 0) {
    pnlText.textColor = redC
  } else {
    pnlText.textColor = textC
  }

  // TODO [Future Expansion]: Render dailyPnL here when available
  // const dailyPnlText = widget.addText("Day PnL: " + formatCurrency(metrics.dailyPnL))
  // dailyPnlText.font = Font.systemFont(14)
  // ... set color logic for dailyPnlText

  widget.addSpacer()

  // Last Updated text at the bottom
  const dateObj = new Date()
  const timeFormatter = new DateFormatter()
  timeFormatter.useShortTimeStyle()
  const timeStr = timeFormatter.string(dateObj)

  const updatedText = widget.addText("Updated: " + timeStr)
  updatedText.font = Font.systemFont(10)
  updatedText.textColor = subTextC
  updatedText.rightAlignText()

  return widget
}

// ----------------------------------------------------
// Main Execution
// ----------------------------------------------------
const positions = await fetchPositions()
const widget = await createWidget(positions)

if (config.runsInWidget) {
  Script.setWidget(widget)
} else {
  // If run directly inside the Scriptable app, show a medium widget preview
  widget.presentSmall()
}

Script.complete()
