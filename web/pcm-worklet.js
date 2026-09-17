// Захват микрофона -> PCM 16 кГц моно Int16, кусочками по 100 мс.
// Никаких библиотек и сети: чистый Web Audio API.
class AilaPcmCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    var opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.chunkSamples = Math.round(this.targetRate / 10);
    this.ratio = sampleRate / this.targetRate;
    this.acc = 0;
    this.count = 0;
    this.phase = 0;
    this.out = new Int16Array(this.chunkSamples);
    this.idx = 0;
  }

  flush() {
    var buf = this.out.buffer;
    this.port.postMessage(buf, [buf]);
    this.out = new Int16Array(this.chunkSamples);
    this.idx = 0;
  }

  process(inputs) {
    var input = inputs[0];
    if (!input || !input.length) return true;
    var ch = input[0];
    if (!ch) return true;
    for (var i = 0; i < ch.length; i++) {
      var v = ch[i];
      this.acc += v;
      this.count++;
      this.phase += 1;
      if (this.phase >= this.ratio) {
        this.phase -= this.ratio;
        var avg = this.count ? this.acc / this.count : 0;
        this.acc = 0;
        this.count = 0;
        if (avg < -1) avg = -1;
        if (avg > 1) avg = 1;
        this.out[this.idx++] = avg < 0 ? avg * 32768 : avg * 32767;
        if (this.idx >= this.chunkSamples) this.flush();
      }
    }
    return true;
  }
}
registerProcessor('aila-pcm', AilaPcmCapture);
