import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Camera, MapPin, Cpu, FileText, ExternalLink } from 'lucide-react'
import { useAssetStore } from '../stores/asset'

function CollapsibleSection({
  icon: Icon,
  title,
  defaultOpen = false,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-400 hover:text-white hover:bg-gray-800/50 transition-colors"
      >
        {open ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
        <Icon className="w-4 h-4 text-indigo-400" />
        <span>{title}</span>
      </button>
      {open && <div className="px-4 pb-3 space-y-1.5">{children}</div>}
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-start gap-4 text-sm">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className="text-gray-200 text-right break-all max-w-[60%]">
        {value ?? <span className="text-gray-500 italic">N/A</span>}
      </span>
    </div>
  )
}

export function MetadataPanel(_props: { assetId: string }) {
  const { t } = useTranslation()
  const asset = useAssetStore((s) => s.currentAsset)
  if (!asset) return <div className="text-sm text-gray-500">Loading metadata...</div>
  const exif = asset.exif || {}
  const tech = asset.custom_metadata || {}
  const camera = (exif.camera as Record<string, string>) || {}
  const gps = (exif.gps as Record<string, number | null>) || {}

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
        <FileText className="w-4 h-4" />
        {t('metadata.title')}
      </h3>
      <div className="space-y-2">
        {/* ── Camera Info ── */}
        <CollapsibleSection icon={Camera} title={t('metadata.camera')}>
          {camera.make || camera.model || camera.lens || camera.software ? (
            <>
              {camera.make && <MetaRow label={t('metadata.make')} value={camera.make} />}
              {camera.model && <MetaRow label={t('metadata.model')} value={camera.model} />}
              {camera.lens && <MetaRow label={t('metadata.lens')} value={camera.lens} />}
              {camera.software && <MetaRow label={t('metadata.software')} value={camera.software} />}
            </>
          ) : (
            <p className="text-sm text-gray-500 italic">{t('metadata.camera_no')}</p>
          )}
        </CollapsibleSection>

        {/* ── Location / GPS ── */}
        <CollapsibleSection icon={MapPin} title={t('metadata.location')}>
          {gps.latitude != null && gps.longitude != null ? (
            <>
              <MetaRow label={t('metadata.latitude')} value={gps.latitude.toFixed(6)} />
              <MetaRow label={t('metadata.longitude')} value={gps.longitude.toFixed(6)} />
              {gps.altitude != null && <MetaRow label={t('metadata.altitude')} value={`${gps.altitude.toFixed(1)} m`} />}
              <div className="pt-1">
                <a
                  href={`https://www.google.com/maps?q=${gps.latitude},${gps.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  {t('metadata.openMap')}
                </a>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-500 italic">{t('metadata.gps_no')}</p>
          )}
        </CollapsibleSection>

        {/* ── Technical Details ── */}
        <CollapsibleSection icon={Cpu} title={t('metadata.technical')}>
          {tech.codec_long_name || tech.pixel_format || tech.format_name ? (
            <>
              {tech.codec_long_name && <MetaRow label={t('metadata.codecLong')} value={tech.codec_long_name as string} />}
              {tech.pixel_format && <MetaRow label={t('metadata.pixelFormat')} value={tech.pixel_format as string} />}
              {tech.color_space && <MetaRow label={t('metadata.colorSpace')} value={tech.color_space as string} />}
              {tech.color_primaries && <MetaRow label={t('metadata.colorPrimaries')} value={tech.color_primaries as string} />}
              {tech.color_transfer && <MetaRow label={t('metadata.colorTransfer')} value={tech.color_transfer as string} />}
              {tech.field_order && <MetaRow label={t('metadata.fieldOrder')} value={tech.field_order as string} />}
              <MetaRow label={t('metadata.isInterlaced')} value={tech.is_interlaced ? t('common.yes') : t('common.no')} />
              {tech.format_name && <MetaRow label={t('metadata.formatName')} value={tech.format_name as string} />}
              {tech.audio_sample_rate != null && (
                <MetaRow label={t('metadata.audioSampleRate')} value={`${tech.audio_sample_rate} ${t('metadata.audioSampleRateHz')}`} />
              )}
              {tech.audio_bitrate != null && (
                <MetaRow label={t('metadata.audioBitrate')} value={`${Math.round((tech.audio_bitrate as number) / 1000)} ${t('metadata.audioBitrateUnit')}`} />
              )}
              {tech.total_bitrate != null && (
                <MetaRow label={t('metadata.bitrate')} value={`${((tech.total_bitrate as number) / 1_000_000).toFixed(2)} ${t('metadata.bitrateUnit')}`} />
              )}
            </>
          ) : (
            <p className="text-sm text-gray-500 italic">{t('metadata.technical_no')}</p>
          )}
        </CollapsibleSection>

        {/* ── File Info ── */}
        <CollapsibleSection icon={FileText} title={t('metadata.fileInfo')}>
          <MetaRow label={t('metadata.originalPath')} value={asset.original_path} />
          {asset.media_date && <MetaRow label={t('metadata.mediaDate')} value={new Date(asset.media_date).toLocaleString()} />}
          {asset.created_at && <MetaRow label={t('metadata.fileCreated')} value={new Date(asset.created_at).toLocaleString()} />}
          {asset.updated_at && <MetaRow label={t('metadata.fileModified')} value={new Date(asset.updated_at).toLocaleString()} />}
        </CollapsibleSection>
      </div>
    </div>
  )
}
