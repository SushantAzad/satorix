import React from 'react'

export function LoadingSpinner({ label, size = 'md' }: { label?: string; size?: 'sm' | 'md' | 'lg' }) {
  const sz = size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-12 w-12' : 'h-8 w-8'
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <svg className={`${sz} animate-spin text-gray-400`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
      {label && <p className="text-sm text-gray-400">{label}</p>}
    </div>
  )
}
