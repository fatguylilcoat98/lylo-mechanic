/**
 * LYLO Mechanic — LoginScreen
 * The Good Neighbor Guard · Built by Christopher Hughes · Sacramento, CA
 * Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
 * Truth · Safety · We Got Your Back
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
} from 'react-native';
import { createClient } from '@supabase/supabase-js';
import ApiClient from '../services/ApiClient';

const SUPABASE_URL = 'https://hcquisslflenechhgqyj.supabase.co';
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || '';

// Lazy initialization to prevent startup crashes
let supabase = null;
const getSupabase = () => {
  if (!supabase) {
    try {
      supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    } catch (error) {
      console.error('[LoginScreen] Failed to initialize Supabase:', error);
      // Return a mock client that will gracefully fail
      return {
        auth: {
          signInWithPassword: () => Promise.reject(new Error('Supabase initialization failed')),
          signUp: () => Promise.reject(new Error('Supabase initialization failed'))
        }
      };
    }
  }
  return supabase;
};

export default function LoginScreen({ navigation }) {
  const [mode, setMode] = useState('login'); // 'login' or 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert('Missing info', 'Please enter your email and password.');
      return;
    }

    setLoading(true);
    try {
      const { data, error } = await getSupabase().auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (error) {
        Alert.alert('Login failed', error.message);
        return;
      }

      // Set the JWT token on the API client
      const token = data.session?.access_token;
      if (token) {
        ApiClient.setAuthToken(token);
        console.log('[LoginScreen] Auth token set, navigating to Connect');
      }

      navigation.replace('Connect');
    } catch (err) {
      Alert.alert('Error', err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async () => {
    if (!email || !password) {
      Alert.alert('Missing info', 'Please enter your email and password.');
      return;
    }

    if (password.length < 6) {
      Alert.alert('Weak password', 'Password must be at least 6 characters.');
      return;
    }

    setLoading(true);
    try {
      const { data, error } = await getSupabase().auth.signUp({
        email: email.trim(),
        password,
      });

      if (error) {
        Alert.alert('Signup failed', error.message);
        return;
      }

      // Some Supabase configs require email confirmation
      if (data.session) {
        ApiClient.setAuthToken(data.session.access_token);
        navigation.replace('Connect');
      } else {
        Alert.alert(
          'Check your email',
          'We sent you a confirmation link. Click it to activate your account, then log in.',
          [{ text: 'OK', onPress: () => setMode('login') }]
        );
      }
    } catch (err) {
      Alert.alert('Error', err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        {/* Logo / Header */}
        <View style={styles.header}>
          <Text style={styles.logo}>🔧</Text>
          <Text style={styles.appName}>LYLO Mechanic</Text>
          <Text style={styles.tagline}>Your honest mechanic in your pocket</Text>
        </View>

        {/* Card */}
        <View style={styles.card}>
          {/* Mode toggle */}
          <View style={styles.modeRow}>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'login' && styles.modeBtnActive]}
              onPress={() => setMode('login')}
            >
              <Text style={[styles.modeBtnText, mode === 'login' && styles.modeBtnTextActive]}>
                Log In
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'signup' && styles.modeBtnActive]}
              onPress={() => setMode('signup')}
            >
              <Text style={[styles.modeBtnText, mode === 'signup' && styles.modeBtnTextActive]}>
                Sign Up
              </Text>
            </TouchableOpacity>
          </View>

          {/* Email */}
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            placeholder="you@example.com"
            placeholderTextColor="#666"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
          />

          {/* Password */}
          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            placeholder={mode === 'signup' ? 'At least 6 characters' : 'Your password'}
            placeholderTextColor="#666"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          />

          {/* Submit */}
          <TouchableOpacity
            style={[styles.submitBtn, loading && styles.submitBtnDisabled]}
            onPress={mode === 'login' ? handleLogin : handleSignup}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.submitBtnText}>
                {mode === 'login' ? 'Log In' : 'Create Account'}
              </Text>
            )}
          </TouchableOpacity>

          {/* Switch mode */}
          <TouchableOpacity
            style={styles.switchMode}
            onPress={() => setMode(mode === 'login' ? 'signup' : 'login')}
          >
            <Text style={styles.switchModeText}>
              {mode === 'login'
                ? "Don't have an account? Sign up free"
                : 'Already have an account? Log in'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Footer */}
        <Text style={styles.footer}>
          Truth · Safety · We Got Your Back
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0f',
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  logo: {
    fontSize: 56,
    marginBottom: 8,
  },
  appName: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.5,
  },
  tagline: {
    fontSize: 14,
    color: '#888',
    marginTop: 6,
  },
  card: {
    backgroundColor: '#16161f',
    borderRadius: 16,
    padding: 24,
    borderWidth: 1,
    borderColor: '#2a2a3a',
  },
  modeRow: {
    flexDirection: 'row',
    marginBottom: 24,
    backgroundColor: '#0a0a0f',
    borderRadius: 10,
    padding: 4,
  },
  modeBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  modeBtnActive: {
    backgroundColor: '#2563eb',
  },
  modeBtnText: {
    color: '#666',
    fontWeight: '600',
    fontSize: 15,
  },
  modeBtnTextActive: {
    color: '#fff',
  },
  label: {
    color: '#aaa',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 6,
    marginTop: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  input: {
    backgroundColor: '#0a0a0f',
    borderWidth: 1,
    borderColor: '#2a2a3a',
    borderRadius: 10,
    color: '#fff',
    fontSize: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 16,
  },
  submitBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  submitBtnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  switchMode: {
    marginTop: 16,
    alignItems: 'center',
  },
  switchModeText: {
    color: '#2563eb',
    fontSize: 14,
  },
  footer: {
    textAlign: 'center',
    color: '#444',
    fontSize: 12,
    marginTop: 32,
  },
});
