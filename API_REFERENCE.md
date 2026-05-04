# New API Endpoints Reference

## Pronunciation Evaluation

### Evaluate User Pronunciation
**Endpoint:** `POST /api/pronunciation/evaluate`

**Parameters:**
- `target_text` (form): Expected text to pronounce
- `audio_file` (file): WebM/MP3 audio from MediaRecorder
- `language` (form): "fr" or "en"

**Response:**
```json
{
  "accuracy": 8,
  "clarity": 7,
  "mistakes": ["pronunciation of 'r'"],
  "feedback": "Generally good, but work on the 'r' sound",
  "improved_version": "bon-ZHOOR (roll the R slightly)",
  "user_text": "bonjour"
}
```

**Status Codes:**
- `200`: Success
- `400`: Missing fields
- `500`: Gemini or audio processing error

---

### Get Pronunciation Guide
**Endpoint:** `GET /api/pronunciation/guide/{word}`

**Parameters:**
- `word` (path): Word to pronounce
- `language` (query): "fr" or "en" (default: "fr")

**Response:**
```json
{
  "word": "bonjour",
  "audio_url": "/audio/guide_bonjour_1715335200.mp3",
  "language": "fr"
}
```

**Note:** Audio URL can be played directly in `<audio>` tag

---

## Vocabulary Management

### Generate Vocabulary Words
**Endpoint:** `POST /api/pronunciation/vocabulary/generate`

**Request Body:**
```json
{
  "level": "B1",
  "count": 5,
  "topic": "travel",
  "language": "fr"
}
```

**Response:**
```json
{
  "words": [
    {
      "word": "voyage",
      "meaning": "trip, journey",
      "example": "Je fais un voyage en France",
      "example_translation": "I'm taking a trip to France",
      "phonetic": "vwah-YAZH",
      "audio_url": "/audio/vocab_fr_voyage_1715335200.mp3"
    }
  ],
  "level": "B1",
  "count": 5
}
```

**CEFR Levels:**
- A1: Elementary
- A2: Elementary
- B1: Intermediate
- B2: Intermediate
- C1: Advanced
- C2: Proficiency

---

### Get Word Progress
**Endpoint:** `GET /api/pronunciation/vocabulary/word/{word}`

**Response:**
```json
{
  "word": "voyage",
  "is_learned": false,
  "practice_count": 3,
  "correct_count": 2,
  "accuracy_score": 7.5,
  "last_practiced": "2026-05-04T10:30:00Z"
}
```

---

### Update Vocabulary Progress
**Endpoint:** `PUT /api/pronunciation/vocabulary/progress`

**Request Body:**
```json
{
  "word": "voyage",
  "is_learned": true,
  "accuracy_score": 8.5
}
```

**Response:**
```json
{
  "word": "voyage",
  "is_learned": true,
  "practice_count": 4,
  "correct_count": 3,
  "accuracy_score": 8.0,
  "last_practiced": "2026-05-04T10:35:00Z"
}
```

**Fields:**
- `word`: Required
- `is_learned`: Optional, true to mark as learned
- `accuracy_score`: Optional, 0-10 pronunciation accuracy

---

## Implementation Examples

### React Component Usage

#### 1. Evaluate Pronunciation
```typescript
const handleEvaluate = async (audioBlob: Blob, targetText: string) => {
  const formData = new FormData();
  formData.append("target_text", targetText);
  formData.append("audio_file", audioBlob, "recording.webm");
  formData.append("language", "fr");

  const response = await fetch("/api/pronunciation/evaluate", {
    method: "POST",
    body: formData
  });

  const evaluation = await response.json();
  console.log(`Accuracy: ${evaluation.accuracy}/10`);
};
```

#### 2. Generate Vocabulary
```typescript
const handleGenerateVocab = async (level: string) => {
  const response = await fetch("/api/pronunciation/vocabulary/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level: level,
      count: 5,
      topic: "food",
      language: "fr"
    })
  });

  const { words } = await response.json();
  return words; // Array of vocabulary items with audio_url
};
```

#### 3. Play Pronunciation Audio
```typescript
const playPronunciation = (word: string) => {
  fetch(`/api/pronunciation/guide/${word}?language=fr`)
    .then(r => r.json())
    .then(data => {
      const audio = new Audio(data.audio_url);
      audio.play();
    });
};
```

#### 4. Update Word Progress
```typescript
const markAsLearned = async (word: string, accuracy: number) => {
  const response = await fetch(
    "/api/pronunciation/vocabulary/progress",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        word: word,
        is_learned: accuracy >= 8,
        accuracy_score: accuracy
      })
    }
  );

  const progress = await response.json();
  console.log(`Practice count: ${progress.practice_count}`);
};
```

---

## Error Handling

### Common Error Responses

**400 Bad Request:**
```json
{
  "detail": "Missing target_text parameter"
}
```

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**404 Not Found:**
```json
{
  "detail": "Word not found"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Evaluation failed"
}
```

---

## Rate Limiting & Quotas

- Gemini API: 15 requests/minute (free tier)
- ElevenLabs API: Based on subscription
- Audio storage: Unlimited (configure AUDIO_STORAGE_PATH)

**Note:** For production, implement rate limiting on FastAPI level

---

## Audio Format Specifications

### Input (from AudioRecorder)
- **Format:** WebM with Opus codec
- **Sample Rate:** 48kHz (browser default)
- **Channels:** Mono
- **Bitrate:** ~32-64 kbps

### Output (from ElevenLabs)
- **Format:** MP3
- **Sample Rate:** Depends on voice (typically 22050 Hz)
- **Channels:** Mono
- **Bitrate:** 32 kbps

### Playback
```typescript
const audio = new Audio(audioUrl);
audio.play();

// Or in HTML
<audio src="/audio/guide_bonjour_12345.mp3" controls />
```

---

## Database Schema

### PronunciationEvaluation
```sql
CREATE TABLE pronunciation_evaluations (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  target_text VARCHAR(500),
  user_text TEXT,
  accuracy FLOAT NOT NULL,
  clarity FLOAT NOT NULL,
  mistakes TEXT,
  feedback TEXT,
  improved_version TEXT,
  audio_url VARCHAR(500),
  language VARCHAR(5),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### VocabularyWord
```sql
CREATE TABLE vocabulary_words (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  word VARCHAR(255) NOT NULL,
  language VARCHAR(5),
  level VARCHAR(5),
  meaning TEXT NOT NULL,
  example TEXT NOT NULL,
  example_translation TEXT,
  phonetic VARCHAR(500),
  audio_url VARCHAR(500),
  is_learned BOOLEAN DEFAULT FALSE,
  practice_count INTEGER DEFAULT 0,
  last_practiced DATETIME,
  correct_count INTEGER DEFAULT 0,
  accuracy_score FLOAT,
  source VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Troubleshooting

### Audio Recording Not Working
1. Check browser console for permission errors
2. Verify HTTPS (required for microphone access)
3. Check browser microphone permissions
4. Clear browser cache

### Gemini API Errors
1. Verify GEMINI_API_KEY is set
2. Check API quota
3. Verify audio file format
4. Check backend logs

### ElevenLabs Audio Not Generating
1. Verify ELEVENLABS_API_KEY is set
2. Check API quota
3. Verify ELEVENLABS_VOICE_ID_FR is set
4. Check network connectivity

### Audio Files Not Serving
1. Verify AUDIO_STORAGE_PATH exists
2. Check file permissions
3. Verify files were written to disk
4. Check nginx/server configuration

---

## Performance Tips

1. **Cache Audio URLs**
   - Store audio_url returned by API
   - Don't regenerate for same text

2. **Batch Vocabulary Generation**
   - Generate multiple words in one request
   - Avoid single-word API calls

3. **Lazy Load Audio**
   - Don't load all audio on page load
   - Load on demand when user interacts

4. **Monitor API Usage**
   - Log API calls for quota tracking
   - Alert when approaching limits

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-04 | Initial release |

---

For questions or issues, check backend logs and frontend console.
