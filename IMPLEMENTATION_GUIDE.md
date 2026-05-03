# TCF Trainer Platform - 7 Major Fixes Implementation Guide

## ✅ COMPLETED

### 1. **Database & Backend Infrastructure**
- ✅ `SpeakingSession` model - tracks conversation context, exchange count, scores
- ✅ `UserAudioResponse` model - stores user audio blobs and transcripts
- ✅ `QuestionValidation` model - validates questions are grounded in source text
- ✅ Enhanced schemas in `backend/schemas.py` for all new features
- ✅ `/tcf/speaking/enhanced/*` routes with conversation memory support
- ✅ Audio blob storage endpoint with Base64 decoding
- ✅ Realistic speaking evaluation (4 scoring criteria)

### 2. **Frontend - Sidebar Layout Fix**
- ✅ Changed from `relative` to `fixed` positioning
- ✅ Width: 240px (consistent across all modules)
- ✅ `height: 100vh` for full-height sticky sidebar
- ✅ Main content has `margin-left: 224px` for proper spacing
- ✅ No more layout shifting or overlap

### 3. **Frontend - Floating AI Assistant Button**
- ✅ New component: `FloatingAIAssistant.tsx`
- ✅ Bottom-right floating button on all modules
- ✅ Chat panel with message history
- ✅ Integrated into `TcfAppShell` (global availability)
- ✅ Mock AI responses (ready to wire real API)

### 4. **Frontend - Speaking Module Improvements (Partial)**
- ✅ Backend routes for conversation memory
- ⏳ **TODO: Frontend UI** - Record conversation exchanges, maintain topic
- ⏳ **TODO: Audio Recording** - Capture user audio blob, send to `/audio/store`
- ⏳ **TODO: Replay Fix** - Already fixed in earlier commit
- ⏳ **TODO: Delay Before Recording** - Add 1.5s pause after examiner audio ends

---

## ⏳ REMAINING WORK (In Priority Order)

### **CRITICAL - Speaking Module (Conversation Engine)**

**File**: `frontend/app/tcf/speaking/page.tsx`

**1. Initialize Session on Load**
```typescript
const handleStartExam = async () => {
  // Call new endpoint: POST /tcf/speaking/enhanced/session/init
  const response = await fetch('/api/tcf/speaking/enhanced/session/init', {
    method: 'POST',
    body: JSON.stringify({
      task_type: selectedTaskType,
      mode: 'practice'
    })
  });
  
  const { session_id, topic, initial_question, initial_audio_url } = await response.json();
  setSessionId(session_id);
  setTopic(topic);
  // Display initial_question and play initial_audio_url
};
```

**2. Add Conversation State**
```typescript
const [conversationContext, setConversationContext] = useState<Array<{
  role: 'examiner' | 'user';
  content: string;
  audio_url?: string;
}>>([]);

const [exchangeCount, setExchangeCount] = useState(0);
const [maxExchangesReached, setMaxExchangesReached] = useState(false);
```

**3. Recording & Submission**
```typescript
const handleSubmitResponse = async () => {
  // Constraints:
  // - Audio recorded during max 5 exchanges
  // - No interruption: wait for examiner audio to end + 1.5s
  // - Store audio blob
  
  // 1. Send audio blob to /tcf/speaking/enhanced/audio/store
  const audioBlob = recordedAudio; // from MediaRecorder
  const base64 = await blobToBase64(audioBlob);
  
  const storeResponse = await fetch('/api/tcf/speaking/enhanced/audio/store', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      exchange_number: exchangeCount,
      audio_data: base64,
      transcript: userTranscript
    })
  });
  
  // 2. Send conversation turn
  const convResponse = await fetch('/api/tcf/speaking/enhanced/conversation', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      message: userTranscript,
      user_audio_url: storeResponse.audio_url,
      history: conversationContext,
      task_type: selectedTaskType,
      exchange_count: exchangeCount
    })
  });
  
  const { reply, audio_url, is_complete } = await convResponse.json();
  
  // 3. Update context
  setConversationContext(prev => [
    ...prev,
    { role: 'user', content: userTranscript, audio_url: storeResponse.audio_url },
    { role: 'examiner', content: reply, audio_url }
  ]);
  
  setExchangeCount(prev => prev + 1);
  if (is_complete) setMaxExchangesReached(true);
};
```

**4. Evaluation with Realistic Scoring**
```typescript
const handleEndSession = async () => {
  const evalResponse = await fetch('/api/tcf/speaking/enhanced/evaluate', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      history: conversationContext,
      task_type: selectedTaskType
    })
  });
  
  const scores = await evalResponse.json();
  // scores contains:
  // - transcription_accuracy: 0-10
  // - grammar_score: 0-10
  // - relevance_score: 0-10
  // - length_score: 0-10
  // - overall_score: weighted average
  // - should_improve: boolean (true if < 6)
  
  setScores(scores);
};
```

---

### **CRITICAL - Writing Module (Step-Based Feedback Flow)**

**File**: `frontend/app/tcf/writing/page.tsx`

**Current Flow** (REMOVE):
- Combined draft section that builds up step by step

**New Flow** (IMPLEMENT):
```
1. User sees Task
   ↓
2. User writes freely in single textarea
   ↓
3. Click "Get Step Feedback"
   - Show: grammar issues, missing points, suggestions
   - Text area remains EDITABLE
   ↓
4. User improves answer in SAME textarea
   ↓
5. Click "Final Evaluation"
   - Show: score, improved version, all suggestions
```

**1. State Changes**
```typescript
// Remove task*Combined states
// Change to simple:
const [task1Text, setTask1Text] = useState("");
const [task2Text, setTask2Text] = useState("");
const [task3Text, setTask3Text] = useState("");

// Feedback stages
const [feedbackStage, setFeedbackStage] = useState<'writing' | 'step-feedback' | 'final'>();
const [stepFeedback, setStepFeedback] = useState(null);
const [finalFeedback, setFinalFeedback] = useState(null);
```

**2. Get Step Feedback**
```typescript
const handleGetStepFeedback = async (taskType: TcfWritingTaskType, text: string) => {
  // Call new endpoint: POST /tcf/writing/step-feedback
  const response = await fetch('/api/tcf/writing/step-feedback', {
    method: 'POST',
    body: JSON.stringify({
      task_type: taskType,
      prompt: currentPrompt,
      user_answer: text
    })
  });
  
  const feedback = await response.json();
  // Returns: {
  //   grammar_issues: [],
  //   missing_points: [],
  //   suggestions: [],
  //   estimated_current_score: 5.2
  // }
  
  setStepFeedback(feedback);
  setFeedbackStage('step-feedback');
};
```

**3. Final Evaluation**
```typescript
const handleFinalEvaluation = async (taskType: TcfWritingTaskType, text: string) => {
  // Call new endpoint: POST /tcf/writing/final-evaluation
  const response = await fetch('/api/tcf/writing/final-evaluation', {
    method: 'POST',
    body: JSON.stringify({
      task_type: taskType,
      prompt: currentPrompt,
      user_answer: text
    })
  });
  
  const evaluation = await response.json();
  // Returns: {
  //   overall_score: 7.5,
  //   grammar_score: 7,
  //   vocabulary_score: 8,
  //   structure_score: 7,
  //   relevance_score: 8,
  //   feedback: [],
  //   improved_version: "...",
  //   final_suggestions: []
  // }
  
  setFinalFeedback(evaluation);
  setFeedbackStage('final');
};
```

**4. UI Components**
- Create `WritingStepFeedbackCard` - shows grammar issues, missing points, suggestions
- Create `WritingFinalEvaluationCard` - shows comprehensive scores and improved version
- Keep textarea editable throughout

---

### **HIGH PRIORITY - Question Validation (Reading & Listening)**

**Backend**: `backend/tcf_ai_service.py`

**Task**: After generating questions, validate that answer is grounded in source text/audio.

```python
def validate_question(question, correct_answer, source_text):
    """
    Ensure answer is grounded in source_text.
    Returns: {
        is_valid: bool,
        validation_score: 0-1,
        source_text_span: str,
        correct_answer_span: str,
        feedback: str
    }
    """
    # 1. Find source span supporting the question
    # 2. Find specific text proving the answer
    # 3. Score confidence 0-1
    # 4. Reject if < 0.7 confidence, regenerate
```

**Frontend**: Display answer span when showing questions (optional highlight)

---

### **HIGH PRIORITY - Login & Protected Dashboard**

**File**: `frontend/app/tcf/dashboard/page.tsx`

**Implementation**:
```typescript
// Add middleware protection
const DashboardPage = () => {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }
    // Optionally validate token
    setUser({ /* ... */ });
    setLoading(false);
  }, []);

  if (loading) return <LoadingSpinner />;
  if (!user) return null;

  return <Dashboard />;
};
```

**Create Login Page**: `frontend/app/login/page.tsx`
```typescript
// Form with:
// - Email input
// - Password input
// - Sign up link
// - Login button
//
// On success:
// - Store token in localStorage
// - Redirect to /tcf/dashboard
```

---

### **MEDIUM PRIORITY - Listening Difficulty Matching**

**Backend**: `backend/routers/tcf_listening_routes.py`

**Task**: Ensure generated question difficulty matches selected level.

```python
def generate_tcf_listening_question(question_number, difficulty_level='all'):
    """
    When difficulty_level is specified (B1, B2, etc):
    - Generate question ONLY from that level's range
    - Validate difficulty in response
    """
    # Current: questions for question_number (1-39)
    # New: if difficulty != 'all', pick random Q from that range
```

---

### **MEDIUM PRIORITY - AI Float Integration with Actual API**

**File**: `frontend/components/FloatingAIAssistant.tsx`

Replace mock response with real API call:

```typescript
const handleSendMessage = async () => {
  // Call actual Learn API or new /api/chat endpoint
  const response = await fetch('/api/learn/chat', {
    method: 'POST',
    body: JSON.stringify({
      message: input,
      context: 'tcf-study', // Current module context
      previous_messages: messages
    })
  });
  
  const { reply } = await response.json();
  // setMessages(...reply);
};
```

---

## 📋 BACKEND DATABASE SETUP

**When user provides PostgreSQL URL**:

```bash
# Set environment variable
export DATABASE_URL="postgresql://user:password@host:port/tcf_db"

# Run migrations (if using Alembic, create migrations first)
# For now, SQLAlchemy will auto-create tables on init_db()

# Verify tables created:
# - users
# - exam_attempts
# - listening_attempts
# - writing_sessions
# - tcf_writing_sessions
# - speaking_sessions (NEW)
# - user_audio_responses (NEW)
# - question_validations (NEW)
# - learn_sessions
```

---

## 🧪 TESTING CHECKLIST

### Speaking Module
- [ ] Session initializes with topic
- [ ] Conversation memory maintains context
- [ ] Max 5 exchanges enforced
- [ ] Audio blob stored correctly
- [ ] Realistic scoring (4 criteria)
- [ ] No repetition of questions

### Writing Module
- [ ] Step feedback shows grammar/missing/suggestions
- [ ] Text area remains editable after feedback
- [ ] Final evaluation shows detailed scores
- [ ] Improved version displayed

### Question Validation
- [ ] Reading questions grounded in passage
- [ ] Listening questions grounded in transcript
- [ ] Invalid questions regenerated

### Sidebar
- [ ] Fixed width (240px) consistent
- [ ] No layout shifting
- [ ] Works on all modules

### AI Float
- [ ] Appears on all pages
- [ ] Chat works
- [ ] Doesn't interfere with page content

### Login
- [ ] Unauth redirects to /login
- [ ] Sign up creates user
- [ ] Login stores token
- [ ] Token persists across pages

---

## 🚀 DEPLOYMENT CHECKLIST

Before deploying to production:

1. **Environment Variables**
   - [ ] `DATABASE_URL` points to PostgreSQL
   - [ ] `GEMINI_API_KEY` configured
   - [ ] `ELEVENLABS_API_KEY` configured
   - [ ] `JWT_SECRET` set to strong value (not "dev_secret_change_me")

2. **Database**
   - [ ] All new tables created
   - [ ] Indexes on frequently queried columns

3. **Frontend**
   - [ ] Sidebar layout tested on all modules
   - [ ] AI float non-intrusive
   - [ ] Login flow working

4. **Backend**
   - [ ] Enhanced speaking endpoints tested
   - [ ] Audio storage working
   - [ ] Question validation active
   - [ ] Writing step feedback operational

5. **Tests**
   - [ ] All modules render without errors
   - [ ] No console warnings
   - [ ] Mobile responsive

---

## 📞 SUPPORT

For issues or clarifications on the implementation:
- Refer to API response examples in `/schemas.py`
- Check route implementations in `/routers/enhanced_speaking.py`
- Review database models in `/models.py`

