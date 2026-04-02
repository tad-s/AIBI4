/**
 * voice.js — MediaRecorder を使った音声録音
 * Safari は webm 非対応なので mp4/ogg にフォールバック
 */
export class VoiceRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.chunks = [];
    this.isRecording = false;
  }

  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = this._preferredMime();
    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    this.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) this.chunks.push(e.data); };
    this.mediaRecorder.start(200);
    this.isRecording = true;
    this._stream = stream;
  }

  stop() {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder) { reject(new Error("Not recording")); return; }
      this.mediaRecorder.onstop = () => {
        const mime = this.mediaRecorder.mimeType || "audio/webm";
        const blob = new Blob(this.chunks, { type: mime });
        this._stream.getTracks().forEach(t => t.stop());
        this.isRecording = false;
        resolve(blob);
      };
      this.mediaRecorder.onerror = e => reject(e.error);
      this.mediaRecorder.stop();
    });
  }

  _preferredMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return types.find(t => MediaRecorder.isTypeSupported(t)) || "";
  }

  static isSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }
}
