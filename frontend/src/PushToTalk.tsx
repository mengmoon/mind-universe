import React, { useState, useRef } from "react"
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib"

const PushToTalk = () => {
  const [recording, setRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunks = useRef<Blob[]>([])

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mediaRecorder = new MediaRecorder(stream)
    mediaRecorderRef.current = mediaRecorder
    audioChunks.current = []

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.current.push(event.data)
      }
    }

    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks.current, { type: "audio/wav" })
      audioBlob.arrayBuffer().then((buffer) => {
        const base64data = btoa(
          new Uint8Array(buffer).reduce((data, byte) => data + String.fromCharCode(byte), "")
        )
        Streamlit.setComponentValue(base64data)
      })
    }

    mediaRecorder.start()
    setRecording(true)
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }

  return (
    <button
      onMouseDown={startRecording}
      onMouseUp={stopRecording}
      onTouchStart={startRecording}
      onTouchEnd={stopRecording}
      style={{
        padding: "12px 24px",
        borderRadius: "50%",
        backgroundColor: recording ? "red" : "green",
        color: "white",
        fontSize: "18px",
        border: "none",
      }}
    >
      🎤
    </button>
  )
}

export default withStreamlitConnection(PushToTalk)
