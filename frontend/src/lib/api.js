export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export function getAuthToken(user) {
	return user?.token || localStorage.getItem('access_token')
}

export function authHeaders(user, extras = {}) {
	const token = getAuthToken(user)
	return {
		...(token ? { Authorization: `Bearer ${token}` } : {}),
		...extras,
	}
}
