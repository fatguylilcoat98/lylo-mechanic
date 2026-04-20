/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React from 'react';
import {StatusBar} from 'expo-status-bar';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';

import LoginScreen from './screens/LoginScreen';
import HomeScreen from './screens/HomeScreen';
import ConnectScreen from './screens/ConnectScreen';
import ScanScreen from './screens/ScanScreen';
import ResultsScreen from './screens/ResultsScreen';
import {C} from './constants/colors';

const Stack = createNativeStackNavigator();

const THEME = {
  dark: true,
  colors: {
    primary: C.accent,
    background: C.bg,
    card: C.card,
    text: C.textBright,
    border: C.border,
    notification: C.accent,
  },
};

export default function App() {
  return (
    <>
      <StatusBar style="light" />
      <NavigationContainer theme={THEME}>
        <Stack.Navigator
          initialRouteName="Login"
          screenOptions={{
            headerStyle: {backgroundColor: C.card},
            headerTintColor: C.accent,
            headerTitleStyle: {fontWeight: '700', letterSpacing: 0.5},
            contentStyle: {backgroundColor: C.bg},
            headerShadowVisible: false,
          }}>
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{headerShown: false}}
          />
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{headerShown: false}}
          />
          <Stack.Screen
            name="Connect"
            component={ConnectScreen}
            options={{title: 'CONNECT OBDLINK'}}
          />
          <Stack.Screen
            name="Scan"
            component={ScanScreen}
            options={{title: 'VEHICLE SCAN'}}
          />
          <Stack.Screen
            name="Results"
            component={ResultsScreen}
            options={{title: 'DIAGNOSIS'}}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </>
  );
}
