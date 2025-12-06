from faster_whisper import WhisperModel
import time
import sys
import numpy as np
import soundfile as sf

# Настройки
AUDIO_PATH = "test.ogg"  # путь к файлу
MODEL_SIZE = "tiny"       # tiny / base / small / medium
BLOCK_DURATION = 5        # секундный размер блока для постепенного вывода

# Модель
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

#  Загружаем звук
audio, sr = sf.read(AUDIO_PATH)
if sr != 16000:
    import librosa
    audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    sr = 16000

# Разбиваем на блоки
samples_per_block = sr * BLOCK_DURATION
num_blocks = int(np.ceil(len(audio) / samples_per_block))

print("Расшифровка началась...\n")

# Поочерёдно транскрибируем куски
for i in range(num_blocks):
    start = int(i * samples_per_block)
    end = int(min((i + 1) * samples_per_block, len(audio)))
    chunk = audio[start:end]

    segments, _ = model.transcribe(chunk, beam_size=1, language="ru")

    for seg in segments:
        text = seg.text.strip()
        if text:
            # имитация "появления" текста, как чат
            for c in text:
                sys.stdout.write(c)
                sys.stdout.flush()
                time.sleep(0.02)
            sys.stdout.write(" ")
            sys.stdout.flush()
    time.sleep(0.5)

print("\n\Расшифровка завершена.")
