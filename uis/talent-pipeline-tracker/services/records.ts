import { request } from "@/services/api";
import { isObject } from "../../../packages/shared/http";
import {
  CandidateInput,
  CandidatePatch,
  CandidateRecord,
  Note,
  NoteInput,
  NotesResponse,
  PaginatedRecordsResponse,
} from "@/types/records";

function validCandidate(value: unknown): boolean {
  return isObject(value) && ["id", "full_name", "email", "phone", "position", "status", "stage", "applied_at", "updated_at"].every((field) => typeof value[field] === "string") && typeof value.notes_count === "number" && typeof value.experience_years === "number" && ["cv_url", "linkedin_url"].every((field) => value[field] == null || typeof value[field] === "string");
}

function validPage(value: unknown): boolean {
  return isObject(value) && typeof value.total === "number" && typeof value.limit === "number" && value.limit > 0 && Array.isArray(value.data) && value.data.every(validCandidate);
}

function validNote(value: unknown): boolean {
  return isObject(value) && ["id", "content", "created_at"].every((field) => typeof value[field] === "string");
}

export async function getAllRecords(): Promise<CandidateRecord[]> {
  const firstPage = await request<PaginatedRecordsResponse>("/records?page=1&limit=50", {}, validPage);

  const records = [...firstPage.data];
  const totalPages = Math.ceil(firstPage.total / firstPage.limit);

  for (let page = 2; page <= totalPages; page += 1) {
    const nextPage = await request<PaginatedRecordsResponse>(`/records?page=${page}&limit=50`, {}, validPage);
    records.push(...nextPage.data);
  }

  return records;
}

export async function getRecordById(id: string): Promise<CandidateRecord> {
  return request<CandidateRecord>(`/records/${id}`, {}, validCandidate);
}

export async function createRecord(payload: CandidateInput): Promise<CandidateRecord> {
  return request<CandidateRecord>("/records", {
    method: "POST",
    body: JSON.stringify(payload),
  }, validCandidate);
}

export async function updateRecord(id: string, payload: CandidateInput): Promise<CandidateRecord> {
  return request<CandidateRecord>(`/records/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, validCandidate);
}

export async function patchRecord(id: string, payload: CandidatePatch): Promise<CandidateRecord> {
  return request<CandidateRecord>(`/records/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }, validCandidate);
}

export async function getNotesByRecord(id: string): Promise<Note[]> {
  const response = await request<NotesResponse>(`/records/${id}/notes`, {}, (value) => isObject(value) && Array.isArray(value.data) && value.data.every(validNote));
  return response.data;
}

export async function addNote(id: string, payload: NoteInput): Promise<Note> {
  return request<Note>(`/records/${id}/notes`, {
    method: "POST",
    body: JSON.stringify(payload),
  }, validNote);
}

export async function deleteNote(id: string, noteId: string): Promise<void> {
  await request<void>(`/records/${id}/notes/${noteId}`, {
    method: "DELETE",
  });
}
