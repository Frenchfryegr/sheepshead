import { inject, Injectable, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Subject } from 'rxjs';

import { environment } from '../../environments/environment';

const RECONNECT_DELAY_MS = 3000;

@Injectable({
  providedIn: 'root',
})
export class GameRealtimeService {
  private isBrowser = isPlatformBrowser(inject(PLATFORM_ID))
  private socket: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private currentGameId: number | null = null

  updates = new Subject<void>()

  private listSocket: WebSocket | null = null
  private listReconnectTimer: ReturnType<typeof setTimeout> | null = null
  private listConnected = false

  listUpdates = new Subject<void>()

  connect(gameId: number) {
    if (!this.isBrowser) return
    this.disconnect()
    this.currentGameId = gameId
    this.open()
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.currentGameId = null
    this.socket?.close()
    this.socket = null
  }

  connectList() {
    if (!this.isBrowser || this.listConnected) return
    this.listConnected = true
    this.openList()
  }

  disconnectList() {
    if (this.listReconnectTimer) {
      clearTimeout(this.listReconnectTimer)
      this.listReconnectTimer = null
    }
    this.listConnected = false
    this.listSocket?.close()
    this.listSocket = null
  }

  private open() {
    if (this.currentGameId == null) return
    const wsUrl = `${environment.apiUrl.replace(/^http/, 'ws')}/ws/games/${this.currentGameId}`
    this.socket = new WebSocket(wsUrl)
    this.socket.onmessage = () => this.updates.next()
    this.socket.onclose = () => this.scheduleReconnect()
  }

  private scheduleReconnect() {
    if (this.currentGameId == null) return
    this.reconnectTimer = setTimeout(() => this.open(), RECONNECT_DELAY_MS)
  }

  private openList() {
    if (!this.listConnected) return
    const wsUrl = `${environment.apiUrl.replace(/^http/, 'ws')}/ws/games`
    this.listSocket = new WebSocket(wsUrl)
    this.listSocket.onmessage = () => this.listUpdates.next()
    this.listSocket.onclose = () => this.scheduleListReconnect()
  }

  private scheduleListReconnect() {
    if (!this.listConnected) return
    this.listReconnectTimer = setTimeout(() => this.openList(), RECONNECT_DELAY_MS)
  }
}
