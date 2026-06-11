import React, { Component, type ReactNode } from 'react'

interface State { hasError: boolean; error: Error | null }
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false, error: null }
  static getDerivedStateFromError(error: Error) { return { hasError: true, error } }
  render() {
    if (this.state.hasError) return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-lg font-medium text-gray-900 mb-2">Something went wrong</p>
        <p className="text-sm text-gray-500 mb-4">{this.state.error?.message}</p>
        <button onClick={() => this.setState({ hasError: false, error: null })} className="px-4 py-2 bg-gray-900 text-white text-sm rounded-lg hover:bg-gray-800">Try again</button>
      </div>
    )
    return this.props.children
  }
}
