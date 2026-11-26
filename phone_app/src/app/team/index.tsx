// Team missions: one piece of work split across several people's assistants, yours leading.
import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useGuard } from '../../lib/guard';
import { useSession } from '../../lib/session';
import { teamLine, teamsOf } from '../../shared/web';
import { Progress } from '../../ui/Progress';
import { Chip, T } from '../../ui/parts';
import { Screen } from '../../ui/Screen';
import { colour, radius } from '../../ui/theme';

export default function Teams() {
  const guard = useGuard();
  const { state } = useSession();
  if (guard || !state) return guard;
  const teams = teamsOf(state) as any[];
  return (
    <Screen title="Team missions" lead="One piece of work, split across several people’s assistants.">
      {!teams.length ? <T v="body">No team missions yet. Your assistant starts one when work is split between two or more people.</T> : null}
      {teams.map(team => (
        <Pressable key={team.context} onPress={() => router.push({ pathname: '/team/[context]', params: { context: team.context } })}
          accessibilityRole="button" accessibilityLabel={`${team.title}. ${teamLine(team)}`}
          style={({ pressed }) => ({ borderWidth: 1, borderColor: colour.line, borderRadius: radius.card, padding: 16, gap: 10, marginBottom: 12, opacity: pressed ? 0.85 : 1 })}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T v="section">{team.title}</T>
            {team.parts.some((p: any) => p.needsYou) ? <Chip label="Needs you" tone="sun" /> : null}
          </View>
          <T v="small">{teamLine(team)}</T>
          <Progress parts={team.parts} />
        </Pressable>
      ))}
    </Screen>
  );
}
