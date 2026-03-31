import React from 'react';
import {StatusBar} from 'expo-status-bar';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';

import HomeScreen from './screens/HomeScreen';
import ConnectScreen from './screens/ConnectScreen';
import ScanScreen from './screens/ScanScreen';
import ResultsScreen from './screens/ResultsScreen';

const Stack = createNativeStackNavigator();

const THEME = {
  dark: true,
  colors: {
    primary: '#D4A843',
    background: '#0D1117',
    card: '#161B22',
    text: '#E6EDF3',
    border: '#30363D',
    notification: '#D4A843',
  },
};

export default function App() {
  return (
    <>
      <StatusBar style="light" />
      <NavigationContainer theme={THEME}>
        <Stack.Navigator
          screenOptions={{
            headerStyle: {backgroundColor: '#161B22'},
            headerTintColor: '#D4A843',
            headerTitleStyle: {fontWeight: '700'},
            contentStyle: {backgroundColor: '#0D1117'},
          }}>
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{title: 'LYLO Mechanic'}}
          />
          <Stack.Screen
            name="Connect"
            component={ConnectScreen}
            options={{title: 'Connect OBDLink'}}
          />
          <Stack.Screen
            name="Scan"
            component={ScanScreen}
            options={{title: 'Vehicle Scan'}}
          />
          <Stack.Screen
            name="Results"
            component={ResultsScreen}
            options={{title: 'Diagnosis'}}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </>
  );
}
