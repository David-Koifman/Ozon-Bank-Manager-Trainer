const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

// Token management
export const getToken = () => {
  return localStorage.getItem('auth_token')
}

export const setToken = (token) => {
  localStorage.setItem('auth_token', token)
}

export const removeToken = () => {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user')
}

export const getUser = () => {
  const userStr = localStorage.getItem('user')
  return userStr ? JSON.parse(userStr) : null
}

export const setUser = (user) => {
  localStorage.setItem('user', JSON.stringify(user))
}

// API fetch with authentication
export const authenticatedFetch = async (url, options = {}) => {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers,
  })
  
  if (response.status === 401) {
    // Token expired or invalid
    removeToken()
    throw new Error('Authentication required')
  }
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || error.message || 'Request failed')
  }
  
  return response.json()
}

// Auth API calls
export const login = async (email) => {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email }),
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(error.detail || error.message || 'Login failed')
  }
  
  const data = await response.json()
  setToken(data.access_token)
  setUser(data.user)
  return data
}

export const register = async (email, name, role = 'manager') => {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, name, role }),
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Registration failed' }))
    throw new Error(error.detail || error.message || 'Registration failed')
  }
  
  const data = await response.json()
  setToken(data.access_token)
  setUser(data.user)
  return data
}

export const getCurrentUser = async () => {
  return authenticatedFetch('/auth/me')
}

export const logout = () => {
  removeToken()
}
