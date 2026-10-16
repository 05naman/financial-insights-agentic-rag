import { useTheme } from '../theme/ThemeContext'
import type { ThemeMode } from '../theme/ThemeContext'
import { MonitorIcon, MoonIcon, SunIcon } from './Icons'

const OPTIONS: { mode: ThemeMode; label: string; Icon: typeof SunIcon }[] = [
  { mode: 'light', label: 'Light theme', Icon: SunIcon },
  { mode: 'system', label: 'Match system theme', Icon: MonitorIcon },
  { mode: 'dark', label: 'Dark theme', Icon: MoonIcon },
]

export default function ThemeToggle() {
  const { mode, setMode } = useTheme()
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-full border border-line bg-surface p-0.5">
      {OPTIONS.map(({ mode: m, label, Icon }) => (
        <button
          key={m}
          role="radio"
          aria-checked={mode === m}
          aria-label={label}
          title={label}
          onClick={() => setMode(m)}
          className={`grid h-7 w-7 place-items-center rounded-full transition duration-150 active:scale-90 ${
            mode === m ? 'bg-ink text-bg' : 'text-muted hover:bg-line/70 hover:text-ink'
          }`}
        >
          <Icon width={15} height={15} />
        </button>
      ))}
    </div>
  )
}
