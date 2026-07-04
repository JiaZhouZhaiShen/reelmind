import { useEffect, useRef } from 'react'
import { useAssetStore } from '../stores/asset'

/**
 * Ctrl+Drag marquee (框选) selection for any page with `[data-asset-id]` elements.
 *
 * @param containerRef - ref to the scroll container that holds the thumbnails.
 *   Events are filtered to only fire when the drag starts inside this container.
 */
export function useMarqueeSelection(containerRef: React.RefObject<HTMLDivElement | null>) {
  const stateRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    lastX: 0,
    lastY: 0,
    ctrlHeld: false,
    initialSelection: [] as string[],
  })

  useEffect(() => {
    let rafId = 0

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      const isCtrl = e.ctrlKey || e.metaKey
      if (!isCtrl) return

      // Only act when container is mounted and click is inside it
      const container = containerRef.current
      if (!container || !container.contains(e.target as Node)) return

      const target = e.target as HTMLElement
      if (target.closest('button, a, input, [data-asset-id]')) return

      e.preventDefault()

      const s = stateRef.current
      s.active = true
      s.startX = e.clientX
      s.startY = e.clientY
      s.lastX = e.clientX
      s.lastY = e.clientY
      s.ctrlHeld = isCtrl
      s.initialSelection = [...useAssetStore.getState().selectedAssetIds]

      const overlay = document.createElement('div')
      overlay.className = 'marquee-overlay'
      overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;'

      const marqueeEl = document.createElement('div')
      marqueeEl.className = 'marquee-rect'
      marqueeEl.style.cssText =
        'position:absolute;border:1px dashed #60a5fa;background:rgba(96,165,250,0.15);pointer-events:none;border-radius:2px;'

      overlay.appendChild(marqueeEl)
      document.body.appendChild(overlay)

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    }

    const onMouseMove = (e: MouseEvent) => {
      const s = stateRef.current
      if (!s.active) return
      s.lastX = e.clientX
      s.lastY = e.clientY

      if (rafId) return
      rafId = requestAnimationFrame(() => {
        rafId = 0
        updateMarquee()
      })
    }

    const updateMarquee = () => {
      const s = stateRef.current
      if (!s.active) return

      const left = Math.min(s.startX, s.lastX)
      const top = Math.min(s.startY, s.lastY)
      const w = Math.abs(s.lastX - s.startX)
      const h = Math.abs(s.lastY - s.startY)

      const marqueeEl = document.querySelector('.marquee-rect') as HTMLElement | null
      if (marqueeEl) {
        marqueeEl.style.left = left + 'px'
        marqueeEl.style.top = top + 'px'
        marqueeEl.style.width = w + 'px'
        marqueeEl.style.height = h + 'px'
      }

      const marqueeBounds = { left, top, right: left + w, bottom: top + h }
      document.querySelectorAll<HTMLElement>('[data-asset-id]').forEach((el) => {
        const rect = el.getBoundingClientRect()
        const intersects = !(
          rect.right < marqueeBounds.left ||
          rect.left > marqueeBounds.right ||
          rect.bottom < marqueeBounds.top ||
          rect.top > marqueeBounds.bottom
        )
        el.classList.toggle('marquee-hover', intersects)
      })
    }

    const onMouseUp = () => {
      const s = stateRef.current
      if (!s.active) return
      s.active = false

      if (rafId) {
        cancelAnimationFrame(rafId)
        rafId = 0
      }

      const left = Math.min(s.startX, s.lastX)
      const top = Math.min(s.startY, s.lastY)
      const w = Math.abs(s.lastX - s.startX)
      const h = Math.abs(s.lastY - s.startY)

      if (w > 5 || h > 5) {
        const marqueeBounds = { left, top, right: left + w, bottom: top + h }

        const intersectedIds: string[] = []
        document.querySelectorAll<HTMLElement>('[data-asset-id]').forEach((el) => {
          const rect = el.getBoundingClientRect()
          const intersects = !(
            rect.right < marqueeBounds.left ||
            rect.left > marqueeBounds.right ||
            rect.bottom < marqueeBounds.top ||
            rect.top > marqueeBounds.bottom
          )
          if (intersects) {
            const id = el.getAttribute('data-asset-id')
            if (id) intersectedIds.push(id)
          }
          el.classList.remove('marquee-hover')
        })

        if (s.ctrlHeld && s.initialSelection.length > 0) {
          const newSel = new Set(s.initialSelection)
          for (const id of intersectedIds) {
            if (newSel.has(id)) {
              newSel.delete(id)
            } else {
              newSel.add(id)
            }
          }
          useAssetStore.getState().selectAllAssets(Array.from(newSel))
        } else {
          useAssetStore.getState().selectAllAssets(intersectedIds)
        }
      }

      document.querySelector('.marquee-overlay')?.remove()
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    // Attach to document, filtered by container containment
    document.addEventListener('mousedown', onMouseDown)

    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.querySelector('.marquee-overlay')?.remove()
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [containerRef])
}
