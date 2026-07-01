import { useRef, useEffect } from "react"

interface YearTimelineProps {
  years: Array<{ year: number; count: number }>
  activeYear: number | null
  activeDayKey: string | null
  onYearClick: (year: number) => void
  onDayClick: (year: number, month: number, day: number) => void
}

export function YearTimeline({
  years,
  activeYear,
  activeDayKey,
  onYearClick,
  onDayClick,
}: YearTimelineProps) {
  const activeItemRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (activeItemRef.current) {
      activeItemRef.current.scrollIntoView({ block: "center", behavior: "smooth" })
    }
  }, [activeYear])

  const sortedYears = [...years].sort((a, b) => b.year - a.year).filter((y) => y.count > 0)

  if (!years.length) return null

  let expandedDayParts: number[] | null = null
  let expandedYearFromDay: number | null = null
  if (activeDayKey) {
    const parts = activeDayKey.split("-").map(Number)
    if (parts.length === 3) {
      expandedYearFromDay = parts[0]
      expandedDayParts = parts
    }
  }

  const showExpandedDate = (year: number) =>
    activeYear === year && expandedYearFromDay === year && expandedDayParts

  return (
    <div className="w-20 bg-gray-950 border-l border-gray-800 flex flex-col items-center py-6 overflow-y-auto select-none scrollbar-none relative h-full">
      <div className="flex flex-col items-center relative">
        {sortedYears.map(({ year, count }, index) => {
          const isActiveYear = year === activeYear
          const showDate = showExpandedDate(year)
          return (
            <div key={year} className="flex flex-col items-center">
              {index > 0 && <div className="w-px h-6 border-l border-dashed border-gray-600" />}

              <div ref={isActiveYear ? activeItemRef : undefined} className="flex flex-col items-center">
                <button
                  onClick={() => onYearClick(year)}
                  className={
                    "w-full px-2 py-2 text-center text-xs transition-all duration-200 relative group flex flex-col items-center gap-1 " +
                    (isActiveYear ? "text-white font-medium" : "text-gray-500 hover:text-gray-300")
                  }
                >
                  {isActiveYear && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-indigo-400 rounded-full shadow-sm shadow-indigo-500/30" />
                  )}
                  <span className="text-sm font-semibold tracking-wider">{year}</span>
                  {!showDate && (
                    <span className="text-[9px] text-gray-600 font-normal leading-none">{count}</span>
                  )}
                </button>

                {showDate && expandedDayParts && (
                  <button
                    onClick={() =>
                      onDayClick(expandedDayParts[0], expandedDayParts[1], expandedDayParts[2])
                    }
                    className="text-indigo-400 text-[11px] font-medium hover:text-indigo-300 transition-colors whitespace-nowrap my-1"
                  >
                    {String(expandedDayParts[1]).padStart(2, "0")} /{" "}
                    {String(expandedDayParts[2]).padStart(2, "0")}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
