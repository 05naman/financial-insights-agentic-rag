import { useEffect, useRef, useState } from 'react'
import { useOnline } from '../hooks/useOnline'

export default function NetworkBanner() {
  const online = useOnline()
  const wasOffline = useRef(false)
  const [backOnline, setBackOnline] = useState(false)

  useEffect(() => {
    if (!online) {
      wasOffline.current = true
      return
    }
    if (!wasOffline.current) return
    wasOffline.current = false
    setBackOnline(true)
    const t = setTimeout(() => setBackOnline(false), 2500)
    return () => clearTimeout(t)
  }, [online])

  if (online && !backOnline) return null
  return (
    <div
      role="status"
      className={`px-4 py-1.5 text-center text-xs font-medium ${
        online ? 'bg-primary-soft text-primary' : 'bg-accent-soft text-accent-ink'
      }`}
    >
      {online ? 'Back online.' : "You're offline. Questions will work again once you reconnect."}
    </div>
  )
}
